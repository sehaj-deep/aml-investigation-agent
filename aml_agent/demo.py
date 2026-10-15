"""Usage limits for the public demo (DEMO_MODE=true), so visitors cannot use up the
owner's model quota. Off everywhere else.

Each live AI action has a daily limit for the whole site, and the copilot also has one
per visitor. Visitors are anonymous: a visitor is a hash of the client address and the
day, so no address is stored. Counts live in Postgres and reset each day (UTC).
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime

from psycopg_pool import AsyncConnectionPool

SCHEMA = """
CREATE TABLE IF NOT EXISTS demo_usage (
    day     DATE NOT NULL,
    kind    TEXT NOT NULL,
    visitor TEXT NOT NULL,
    n       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, kind, visitor)
);
"""

# kind: (per visitor per day or None, whole site per day)
LIMITS: dict[str, tuple[int | None, int]] = {
    "copilot": (3, 100),
    "sar_draft": (2, 20),
    "reinvestigate": (1, 10),
}
MESSAGES = {
    "copilot": "copilot questions",
    "sar_draft": "AI SAR drafts",
    "reinvestigate": "AI re-investigations",
}


class LimitReached(RuntimeError):
    """A demo limit is reached; the message says which and when it resets."""


def enabled() -> bool:
    return os.environ.get("DEMO_MODE", "false").lower() == "true"


def visitor_id(client: str | None) -> str:
    day = datetime.now(UTC).date().isoformat()
    return hashlib.sha256(f"{client or 'unknown'}|{day}".encode()).hexdigest()[:16]


def trusted_hops() -> int:
    """How many X-Forwarded-For entries at the end were added by our own proxies (the
    host's front end and nginx). The visitor's address is the entry just before them; any
    entries before that were sent by the client and can be forged."""
    return int(os.environ.get("DEMO_TRUSTED_PROXY_HOPS", "1"))


def forwarded_entries(headers) -> list[str]:
    forwarded = headers.get("x-forwarded-for") or ""
    return [e.strip() for e in forwarded.split(",") if e.strip()]


def client_address(headers, fallback: str | None) -> str | None:
    """The visitor's address: the X-Forwarded-For entry added by the first trusted proxy.
    Taking the first entry instead would let a visitor forge a new identity per request."""
    entries = forwarded_entries(headers)
    hops = trusted_hops()
    if len(entries) > hops:
        return entries[-(hops + 1)]
    return entries[0] if entries else fallback


async def init(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        await conn.execute(SCHEMA)


async def use(pool: AsyncConnectionPool, kind: str, visitor: str) -> None:
    """Count one use, or raise LimitReached. Does nothing outside demo mode."""
    if not enabled():
        return
    per_visitor, per_site = LIMITS[kind]
    day = datetime.now(UTC).date()
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ["demo:" + kind])
        site = await (
            await conn.execute(
                "SELECT COALESCE(sum(n), 0) AS n FROM demo_usage WHERE day = %s AND kind = %s",
                [day, kind],
            )
        ).fetchone()
        mine = await (
            await conn.execute(
                "SELECT COALESCE(sum(n), 0) AS n FROM demo_usage "
                "WHERE day = %s AND kind = %s AND visitor = %s",
                [day, kind, visitor],
            )
        ).fetchone()
        what = MESSAGES[kind]
        if site["n"] >= per_site:
            raise LimitReached(
                f"The demo's daily limit of {per_site} {what} is reached. It resets at "
                "midnight UTC; the reviewed cases stay available."
            )
        if per_visitor is not None and mine["n"] >= per_visitor:
            raise LimitReached(
                f"You have used your {per_visitor} {what} for today in this demo. Thank you "
                "for trying it; the reviewed cases stay available."
            )
        await conn.execute(
            "INSERT INTO demo_usage (day, kind, visitor, n) VALUES (%s, %s, %s, 1) "
            "ON CONFLICT (day, kind, visitor) DO UPDATE SET n = demo_usage.n + 1",
            [day, kind, visitor],
        )


async def status(pool: AsyncConnectionPool, visitor: str) -> dict:
    """What a visitor has left today, for the screen."""
    if not enabled():
        return {"demo": False}
    day = datetime.now(UTC).date()
    async with pool.connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT kind, COALESCE(sum(n), 0) AS site, "
                "COALESCE(sum(n) FILTER (WHERE visitor = %s), 0) AS mine "
                "FROM demo_usage WHERE day = %s GROUP BY kind",
                [visitor, day],
            )
        ).fetchall()
    used = {r["kind"]: r for r in rows}
    left = {}
    for kind, (per_visitor, per_site) in LIMITS.items():
        site_left = per_site - int(used.get(kind, {}).get("site", 0))
        mine_left = (
            per_visitor - int(used.get(kind, {}).get("mine", 0)) if per_visitor else site_left
        )
        left[kind] = max(0, min(site_left, mine_left))
    return {"demo": True, "left": left, "limits": {k: v[0] or v[1] for k, v in LIMITS.items()}}
