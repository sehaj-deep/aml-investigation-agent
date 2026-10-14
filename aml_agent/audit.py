"""Append-only audit log (FR-6) and case reconstruction from it.

Every tool call (inputs, outputs, timing), model call (provider, model tag, prompt
version, tokens, the reply), workflow state change and human decision is one row.
Rows form a per-case hash chain, and Postgres triggers block UPDATE, DELETE and
TRUNCATE. (A database superuser can still drop the triggers; see the threat model.)

`reconstruct(events)` rebuilds a case's workflow state from the log alone.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from psycopg.types.json import Jsonb

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    event_id   BIGSERIAL PRIMARY KEY,
    case_id    TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor      TEXT NOT NULL,
    payload    JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    prev_hash  TEXT,
    hash       TEXT NOT NULL,
    UNIQUE (case_id, seq)
);
CREATE OR REPLACE FUNCTION audit_log_block() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not allowed', TG_OP;
END;
$$;
DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit_log;
CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_block();
DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log;
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_block();
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM PUBLIC;
"""


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def event_hash(
    prev_hash: str | None, case_id: str, seq: int, event_type: str, actor: str, payload: Any
) -> str:
    body = canonical(
        {
            "prev": prev_hash,
            "case_id": case_id,
            "seq": seq,
            "type": event_type,
            "actor": actor,
            "payload": payload,
        }
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class AuditSink(Protocol):
    async def emit(
        self, case_id: str, event_type: str, payload: dict, actor: str = "agent"
    ) -> None: ...


class MemoryAudit:
    """In-memory sink for tests; same chain rules as Postgres."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def emit(
        self, case_id: str, event_type: str, payload: dict, actor: str = "agent"
    ) -> None:
        payload = json.loads(canonical(payload))
        prior = [e for e in self.events if e["case_id"] == case_id]
        prev = prior[-1]["hash"] if prior else None
        seq = len(prior) + 1
        self.events.append(
            {
                "case_id": case_id,
                "seq": seq,
                "event_type": event_type,
                "actor": actor,
                "payload": payload,
                "prev_hash": prev,
                "hash": event_hash(prev, case_id, seq, event_type, actor, payload),
            }
        )

    def for_case(self, case_id: str) -> list[dict]:
        return [e for e in self.events if e["case_id"] == case_id]


class PostgresAudit:
    def __init__(self, pool) -> None:
        self.pool = pool

    async def init_schema(self) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(SCHEMA)

    async def emit(
        self, case_id: str, event_type: str, payload: dict, actor: str = "agent"
    ) -> None:
        payload = json.loads(canonical(payload))
        async with self.pool.connection() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [case_id])
            last = await (
                await conn.execute(
                    "SELECT seq, hash FROM audit_log WHERE case_id = %s ORDER BY seq DESC LIMIT 1",
                    [case_id],
                )
            ).fetchone()
            seq = (last["seq"] if last else 0) + 1
            prev = last["hash"] if last else None
            await conn.execute(
                "INSERT INTO audit_log (case_id, seq, event_type, actor, payload, prev_hash, hash)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                [
                    case_id,
                    seq,
                    event_type,
                    actor,
                    Jsonb(payload),
                    prev,
                    event_hash(prev, case_id, seq, event_type, actor, payload),
                ],
            )

    async def events(self, case_id: str) -> list[dict]:
        async with self.pool.connection() as conn:
            return await (
                await conn.execute(
                    "SELECT case_id, seq, event_type, actor, payload, created_at, prev_hash, hash"
                    " FROM audit_log WHERE case_id = %s ORDER BY seq",
                    [case_id],
                )
            ).fetchall()


def verify_chain(events: list[dict]) -> bool:
    """True if seq is gapless and every hash matches its content and predecessor."""
    prev = None
    for i, e in enumerate(events, start=1):
        if e["seq"] != i or e["prev_hash"] != prev:
            return False
        expected = event_hash(
            prev, e["case_id"], e["seq"], e["event_type"], e["actor"], e["payload"]
        )
        if e["hash"] != expected:
            return False
        prev = e["hash"]
    return True


LIST_FIELDS = ("messages", "tool_log", "seen_tx_ids", "warnings", "decisions", "cited_tx_ids")


def state_delta(before: dict, update: dict) -> dict:
    """Compact description of a node's state update: appended list items, other fields."""
    appended: dict[str, list] = {}
    replaced: dict[str, Any] = {}
    for key, value in update.items():
        old = before.get(key)
        if (
            key in LIST_FIELDS
            and isinstance(value, list)
            and isinstance(old, list)
            and value[: len(old)] == old
        ):
            appended[key] = value[len(old) :]
        else:
            replaced[key] = value
    return {"append": appended, "set": replaced}


def reconstruct(events: list[dict]) -> dict:
    """Rebuild the workflow state from audit events alone."""
    state: dict[str, Any] = {}
    for e in events:
        if e["event_type"] == "case_started":
            state.update(e["payload"]["input"])
        elif e["event_type"] == "node_finished":
            delta = e["payload"]["delta"]
            for key, value in delta["set"].items():
                state[key] = value
            for key, items in delta["append"].items():
                state[key] = [*state.get(key, []), *items]
    return state


def timeline(events: list[dict]) -> list[str]:
    """Human-readable lines for a case, from the log alone."""
    lines = []
    for e in events:
        p = e["payload"]
        t = e["event_type"]
        if t == "tool_call":
            detail = f"{p['name']} ok={p['ok']} {p['duration_ms']} ms"
        elif t == "model_call":
            detail = (
                f"{p['provider']}/{p['model']} prompt {p['prompt_version']} "
                f"in={p['input_tokens']} out={p['output_tokens']} "
                f"tool_calls={len(p['reply'].get('tool_calls', []))}"
            )
        elif t in ("node_started", "node_finished", "node_interrupted", "node_failed"):
            detail = p["node"]
        elif t in ("decision_recorded", "decision_applied"):
            detail = f"{p['action']} by {p['reviewer']}: {p['reason']}"
        elif t == "status":
            detail = p["status"]
        else:
            detail = ""
        lines.append(f"{e['seq']:>4} {e['actor']:<8} {t:<18} {detail}")
    return lines
