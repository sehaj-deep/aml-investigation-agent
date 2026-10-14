"""Postgres case store and work queue (cases, decisions).

Case status flow:
    queued -> running -> pending_review -> decision_recorded -> running
           -> approved | rejected   (or back to pending_review after "request more")
    any running case can become failed.
Workers claim cases with FOR UPDATE SKIP LOCKED and a lease, so a case whose
worker died is picked up again by the next worker.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from aml_agent import config  # noqa: F401  (loads .env)
from aml_agent.schemas.case import Decision

FINAL_STATUSES = ("approved", "rejected")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id        TEXT PRIMARY KEY,
    alert_id       TEXT NOT NULL,
    alert          JSONB NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('queued', 'running', 'pending_review',
                       'decision_recorded', 'approved', 'rejected', 'failed')),
    run_phase      TEXT NOT NULL DEFAULT 'start' CHECK (run_phase IN ('start', 'resume')),
    draft          JSONB,
    warnings       JSONB NOT NULL DEFAULT '[]',
    metrics        JSONB NOT NULL DEFAULT '{}',
    error          TEXT,
    provider       TEXT,
    model          TEXT,
    prompt_version TEXT,
    claimed_by     TEXT,
    claimed_at     TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cases_status_idx ON cases (status, updated_at);
CREATE TABLE IF NOT EXISTS decisions (
    decision_id BIGSERIAL PRIMARY KEY,
    case_id     TEXT NOT NULL REFERENCES cases (case_id),
    action      TEXT NOT NULL CHECK (action IN ('approve', 'reject', 'request_more')),
    reason      TEXT NOT NULL,
    reviewer    TEXT NOT NULL,
    decided_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at  TIMESTAMPTZ
);
"""


class CaseStateError(RuntimeError):
    """An action that the case's current status does not allow."""


def database_url() -> str:
    if url := os.environ.get("DATABASE_URL"):
        return url
    user = os.environ.get("POSTGRES_USER", "aml")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "aml")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def make_pool(url: str | None = None) -> AsyncConnectionPool:
    return AsyncConnectionPool(
        url or database_url(),
        min_size=1,
        max_size=5,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )


async def init_schema(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        await conn.execute(SCHEMA)


async def create_case(pool: AsyncConnectionPool, alert: dict[str, Any]) -> str:
    case_id = f"case-{uuid.uuid4().hex[:12]}"
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO cases (case_id, alert_id, alert, status) VALUES (%s, %s, %s, 'queued')",
            [case_id, alert["alert_id"], Jsonb(alert)],
        )
    return case_id


async def get_case(pool: AsyncConnectionPool, case_id: str) -> dict | None:
    async with pool.connection() as conn:
        case = await (
            await conn.execute("SELECT * FROM cases WHERE case_id = %s", [case_id])
        ).fetchone()
        if case is None:
            return None
        case["decisions"] = await (
            await conn.execute(
                "SELECT action, reason, reviewer, decided_at, applied_at FROM decisions "
                "WHERE case_id = %s ORDER BY decision_id",
                [case_id],
            )
        ).fetchall()
        return case


async def list_cases(pool: AsyncConnectionPool, status: str | None = None) -> list[dict]:
    sql = "SELECT case_id, alert_id, status, model, created_at, updated_at FROM cases"
    params: list = []
    if status:
        sql += " WHERE status = %s"
        params.append(status)
    sql += " ORDER BY created_at"
    async with pool.connection() as conn:
        return await (await conn.execute(sql, params)).fetchall()


async def record_decision(pool: AsyncConnectionPool, case_id: str, decision: Decision) -> None:
    """Record a human decision. Only a case waiting for review accepts one."""
    async with pool.connection() as conn, conn.transaction():
        row = await (
            await conn.execute("SELECT status FROM cases WHERE case_id = %s FOR UPDATE", [case_id])
        ).fetchone()
        if row is None:
            raise KeyError(case_id)
        if row["status"] != "pending_review":
            raise CaseStateError(f"case is {row['status']}, not pending_review")
        await conn.execute(
            "INSERT INTO decisions (case_id, action, reason, reviewer) VALUES (%s, %s, %s, %s)",
            [case_id, decision.action, decision.reason, decision.reviewer],
        )
        await conn.execute(
            "UPDATE cases SET status = 'decision_recorded', run_phase = 'resume', "
            "updated_at = now() WHERE case_id = %s",
            [case_id],
        )


async def claim_next(
    pool: AsyncConnectionPool, worker_id: str, lease_seconds: int = 600
) -> dict | None:
    async with pool.connection() as conn, conn.transaction():
        row = await (
            await conn.execute(
                """
                SELECT case_id, run_phase, alert FROM cases
                WHERE status IN ('queued', 'decision_recorded')
                   OR (status = 'running' AND claimed_at < now() - make_interval(secs => %s))
                ORDER BY updated_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                [lease_seconds],
            )
        ).fetchone()
        if row is None:
            return None
        await conn.execute(
            "UPDATE cases SET status = 'running', claimed_by = %s, claimed_at = now(), "
            "updated_at = now() WHERE case_id = %s",
            [worker_id, row["case_id"]],
        )
        return row


async def next_decision(pool: AsyncConnectionPool, case_id: str) -> dict | None:
    async with pool.connection() as conn:
        return await (
            await conn.execute(
                "SELECT decision_id, action, reason, reviewer, decided_at FROM decisions "
                "WHERE case_id = %s AND applied_at IS NULL ORDER BY decision_id LIMIT 1",
                [case_id],
            )
        ).fetchone()


async def mark_decision_applied(pool: AsyncConnectionPool, decision_id: int) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE decisions SET applied_at = now() WHERE decision_id = %s", [decision_id]
        )


async def save_progress(
    pool: AsyncConnectionPool, case_id: str, status: str, values: dict, metrics: dict
) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE cases SET status = %s, draft = %s, warnings = %s, metrics = %s,
                   provider = %s, model = %s, prompt_version = %s,
                   claimed_by = NULL, claimed_at = NULL, error = NULL, updated_at = now()
            WHERE case_id = %s
            """,
            [
                status,
                Jsonb(values.get("case")),
                Jsonb(values.get("warnings", [])),
                Jsonb(metrics),
                values.get("provider"),
                values.get("model"),
                values.get("prompt_version"),
                case_id,
            ],
        )


async def mark_failed(pool: AsyncConnectionPool, case_id: str, error: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE cases SET status = 'failed', error = %s, claimed_by = NULL, "
            "claimed_at = NULL, updated_at = now() WHERE case_id = %s",
            [error[:4000], case_id],
        )
