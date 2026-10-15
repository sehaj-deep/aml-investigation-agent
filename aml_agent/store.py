"""Postgres case store and work queue (cases, decisions).

Case status flow:
    queued -> running -> pending_review -> decision_recorded -> running -> then
      close         -> closed
      request_more  -> running (the AI investigates again) -> pending_review
      escalate      -> pending_approval -> decision_recorded -> running -> then
          confirm_escalation (a supervisor, not the escalating reviewer) -> escalated
          return_to_analyst                                             -> pending_review
    any running case can become failed.
Workers claim cases with FOR UPDATE SKIP LOCKED and a lease, so a case whose
worker died is picked up again by the next worker.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterable
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from aml_agent import config  # noqa: F401  (loads .env)
from aml_agent.schemas.case import ANALYST_ACTIONS, SUPERVISOR_ACTIONS, Decision

FINAL_STATUSES = ("closed", "escalated")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id        TEXT PRIMARY KEY,
    alert_id       TEXT NOT NULL,
    alert          JSONB NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('queued', 'running', 'pending_review',
                       'decision_recorded', 'pending_approval', 'closed', 'escalated',
                       'failed')),
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
ALTER TABLE cases ADD COLUMN IF NOT EXISTS verification JSONB;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS case_graph JSONB;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS analysis JSONB;
CREATE TABLE IF NOT EXISTS alerts (
    alert_id     TEXT PRIMARY KEY,
    seed_bank    INTEGER NOT NULL,
    seed_account TEXT NOT NULL,
    window_start TIMESTAMP NOT NULL,
    window_end   TIMESTAMP NOT NULL,
    score        DOUBLE PRECISION,
    rank         INTEGER,
    priority     TEXT,
    n_triggers   INTEGER NOT NULL DEFAULT 0,
    alert        JSONB NOT NULL,
    loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS alerts_rank_idx ON alerts (rank);
CREATE INDEX IF NOT EXISTS alerts_priority_idx ON alerts (priority, rank);
CREATE INDEX IF NOT EXISTS cases_alert_idx ON cases (alert_id, created_at);
CREATE TABLE IF NOT EXISTS copilot_messages (
    id            BIGSERIAL PRIMARY KEY,
    case_id       TEXT NOT NULL REFERENCES cases (case_id),
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    tools         JSONB NOT NULL DEFAULT '[]',
    cited         JSONB NOT NULL DEFAULT '[]',
    unverified    JSONB NOT NULL DEFAULT '[]',
    model         TEXT,
    version       TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    seconds       REAL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS copilot_case_idx ON copilot_messages (case_id, id);
CREATE TABLE IF NOT EXISTS sar_drafts (
    id          BIGSERIAL PRIMARY KEY,
    case_id     TEXT NOT NULL REFERENCES cases (case_id),
    version_no  INTEGER NOT NULL,
    sections    JSONB NOT NULL,
    facts       JSONB NOT NULL,
    warnings    JSONB NOT NULL DEFAULT '[]',
    source      TEXT NOT NULL CHECK (source IN ('ai', 'analyst')),
    author      TEXT NOT NULL,
    role        TEXT,
    model       TEXT,
    version     TEXT,
    tokens      INTEGER,
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved')),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (case_id, version_no)
);
CREATE TABLE IF NOT EXISTS decisions (
    decision_id BIGSERIAL PRIMARY KEY,
    case_id     TEXT NOT NULL REFERENCES cases (case_id),
    action      TEXT NOT NULL CHECK (action IN ('close', 'escalate', 'request_more',
                    'confirm_escalation', 'return_to_analyst')),
    reason      TEXT NOT NULL,
    reviewer    TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'analyst' CHECK (role IN ('analyst', 'supervisor')),
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


async def load_alerts(pool: AsyncConnectionPool, alerts: Iterable[dict[str, Any]]) -> int:
    """Replace the monitoring queue with these alerts (alert JSON as in Alert),
    streamed, so the whole queue is never held in memory."""
    n = 0
    async with pool.connection() as conn, conn.transaction():
        await conn.execute(
            "CREATE TEMP TABLE alerts_in (LIKE alerts INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        cur = conn.cursor()
        async with cur.copy(
            "COPY alerts_in (alert_id, seed_bank, seed_account, window_start, window_end, "
            "score, rank, priority, n_triggers, alert) FROM STDIN"
        ) as copy:
            for a in alerts:
                await copy.write_row(
                    [
                        a["alert_id"],
                        a["seed_bank"],
                        a["seed_account"],
                        a["window_start"],
                        a["window_end"],
                        a.get("detection_score"),
                        a.get("detection_rank"),
                        a.get("priority"),
                        len(a.get("trigger_tx_ids") or []),
                        Jsonb(a),
                    ]
                )
                n += 1
        await conn.execute(
            """
            INSERT INTO alerts SELECT * FROM alerts_in
            ON CONFLICT (alert_id) DO UPDATE SET
                seed_bank = EXCLUDED.seed_bank, seed_account = EXCLUDED.seed_account,
                window_start = EXCLUDED.window_start, window_end = EXCLUDED.window_end,
                score = EXCLUDED.score, rank = EXCLUDED.rank, priority = EXCLUDED.priority,
                n_triggers = EXCLUDED.n_triggers, alert = EXCLUDED.alert,
                loaded_at = EXCLUDED.loaded_at
            """
        )
        # The queue is replaced as a whole: alerts no longer raised leave it (their cases,
        # if any, keep a copy of the alert).
        await conn.execute(
            "DELETE FROM alerts WHERE alert_id NOT IN (SELECT alert_id FROM alerts_in)"
        )
    return n


async def count_alerts(pool: AsyncConnectionPool) -> int:
    async with pool.connection() as conn:
        row = await (await conn.execute("SELECT count(*) AS n FROM alerts")).fetchone()
        return row["n"]


# An alert's work status comes from its latest case; "new" when nobody opened it yet.
_ALERT_ROWS = """
    SELECT a.alert_id, a.seed_bank, a.seed_account, a.window_start, a.window_end,
           a.score, a.rank, a.priority, a.n_triggers,
           a.alert->'detection_factors' AS reasons,
           c.case_id, COALESCE(c.status, 'new') AS status,
           c.draft->>'recommended_action' AS recommended_action,
           c.draft->>'pattern_hypothesis' AS pattern,
           c.updated_at AS case_updated_at
    FROM alerts a
    LEFT JOIN LATERAL (
        SELECT case_id, status, draft, updated_at FROM cases
        WHERE cases.alert_id = a.alert_id ORDER BY created_at DESC LIMIT 1
    ) c ON true
"""


async def list_alerts(
    pool: AsyncConnectionPool,
    priority: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """One page of the alert queue, highest score first, with its total size."""
    where, params = [], []
    if priority:
        where.append("priority = %s")
        params.append(priority)
    if status == "open":
        where.append("status NOT IN ('closed', 'escalated')")
    elif status:
        where.append("status = %s")
        params.append(status)
    if search:
        where.append("(alert_id ILIKE %s OR seed_account ILIKE %s OR case_id ILIKE %s)")
        params += [f"%{search}%"] * 3
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"SELECT * FROM ({_ALERT_ROWS}) q {clause}"
    async with pool.connection() as conn:
        total = await (
            await conn.execute(f"SELECT count(*) AS n FROM ({sql}) t", params)
        ).fetchone()
        items = await (
            await conn.execute(f"{sql} ORDER BY rank LIMIT %s OFFSET %s", [*params, limit, offset])
        ).fetchall()
    return {"total": total["n"], "items": items}


async def get_alert(pool: AsyncConnectionPool, alert_id: str) -> dict | None:
    async with pool.connection() as conn:
        row = await (
            await conn.execute(
                f"SELECT q.*, a.alert FROM ({_ALERT_ROWS}) q "
                "JOIN alerts a USING (alert_id) WHERE alert_id = %s",
                [alert_id],
            )
        ).fetchone()
        return row


async def open_alert(pool: AsyncConnectionPool, alert_id: str) -> tuple[str, bool] | None:
    """The alert's case, created (queued for the AI review) on first open.

    Returns (case_id, created), or None if the alert does not exist. Concurrent opens of
    the same alert get the same case.
    """
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [alert_id])
        alert = await (
            await conn.execute("SELECT alert FROM alerts WHERE alert_id = %s", [alert_id])
        ).fetchone()
        if alert is None:
            return None
        case = await (
            await conn.execute(
                "SELECT case_id FROM cases WHERE alert_id = %s ORDER BY created_at DESC LIMIT 1",
                [alert_id],
            )
        ).fetchone()
        if case:
            return case["case_id"], False
        case_id = f"case-{uuid.uuid4().hex[:12]}"
        await conn.execute(
            "INSERT INTO cases (case_id, alert_id, alert, status) VALUES (%s, %s, %s, 'queued')",
            [case_id, alert_id, Jsonb(alert["alert"])],
        )
        return case_id, True


async def alert_summary(pool: AsyncConnectionPool) -> dict:
    """Queue counts by priority and by work status, for the operations dashboard."""
    async with pool.connection() as conn:
        rows = await (
            await conn.execute(
                f"SELECT priority, status, count(*) AS n FROM ({_ALERT_ROWS}) q GROUP BY 1, 2"
            )
        ).fetchall()
    by_priority: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for r in rows:
        by_priority[r["priority"] or "none"] = by_priority.get(r["priority"] or "none", 0) + r["n"]
        by_status[r["status"]] = by_status.get(r["status"], 0) + r["n"]
    return {"total": sum(by_status.values()), "by_priority": by_priority, "by_status": by_status}


async def save_case_file(pool: AsyncConnectionPool, case_id: str, values: dict) -> None:
    """Store the code-built case file as soon as it exists, while the AI review runs."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE cases SET case_graph = %s, analysis = %s, provider = %s, model = %s,
                   prompt_version = %s, updated_at = now()
            WHERE case_id = %s
            """,
            [
                Jsonb(values.get("case_graph")),
                Jsonb(_analysis(values)),
                values.get("provider"),
                values.get("model"),
                values.get("prompt_version"),
                case_id,
            ],
        )


def _analysis(values: dict) -> dict:
    return {
        "hypothesis": values.get("hypothesis"),
        "candidates": values.get("candidates", []),
        "risk": values.get("risk"),
        "aliases": values.get("aliases", {}),
        "triggers": values.get("triggers", []),
        "case_file": values.get("case_file"),
        "guidance": values.get("guidance", []),
    }


async def save_copilot_answer(pool: AsyncConnectionPool, case_id: str, a: dict) -> int:
    async with pool.connection() as conn:
        row = await (
            await conn.execute(
                """
                INSERT INTO copilot_messages (case_id, question, answer, tools, cited, unverified,
                    model, version, input_tokens, output_tokens, seconds)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                [
                    case_id,
                    a["question"],
                    a["answer"],
                    Jsonb(a["tools"]),
                    Jsonb(a["cited"]),
                    Jsonb(a["unverified"]),
                    a["model"],
                    a["version"],
                    a["input_tokens"],
                    a["output_tokens"],
                    a["seconds"],
                ],
            )
        ).fetchone()
        return row["id"]


async def copilot_history(pool: AsyncConnectionPool, case_id: str) -> list[dict]:
    async with pool.connection() as conn:
        return await (
            await conn.execute(
                "SELECT id, question, answer, tools, cited, unverified, created_at "
                "FROM copilot_messages WHERE case_id = %s ORDER BY id",
                [case_id],
            )
        ).fetchall()


async def latest_sar(pool: AsyncConnectionPool, case_id: str) -> dict:
    """The latest SAR draft version of a case, with version counts."""
    async with pool.connection() as conn:
        latest = await (
            await conn.execute(
                "SELECT * FROM sar_drafts WHERE case_id = %s ORDER BY version_no DESC LIMIT 1",
                [case_id],
            )
        ).fetchone()
        counts = await (
            await conn.execute(
                "SELECT count(*) AS versions, count(*) FILTER (WHERE source = 'ai') AS ai_drafts "
                "FROM sar_drafts WHERE case_id = %s",
                [case_id],
            )
        ).fetchone()
    return {"sar": latest, **counts}


async def add_sar_version(pool: AsyncConnectionPool, case_id: str, v: dict) -> dict:
    """Save a new SAR draft version. An approved report is final."""
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ["sar:" + case_id])
        last = await (
            await conn.execute(
                "SELECT version_no, status FROM sar_drafts WHERE case_id = %s "
                "ORDER BY version_no DESC LIMIT 1",
                [case_id],
            )
        ).fetchone()
        if last and last["status"] == "approved":
            raise CaseStateError("the report is approved and can no longer be edited")
        return await (
            await conn.execute(
                """
                INSERT INTO sar_drafts (case_id, version_no, sections, facts, warnings, source,
                    author, role, model, version, tokens)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
                """,
                [
                    case_id,
                    (last["version_no"] if last else 0) + 1,
                    Jsonb(v["sections"]),
                    Jsonb(v["facts"]),
                    Jsonb(v["warnings"]),
                    v["source"],
                    v["author"],
                    v.get("role"),
                    v.get("model"),
                    v.get("version"),
                    v.get("tokens"),
                ],
            )
        ).fetchone()


async def approve_sar(pool: AsyncConnectionPool, case_id: str, reviewer: str, role: str) -> dict:
    """Four-eyes approval of the latest version: a supervisor who did not write it, and
    only after an analyst has reviewed and saved the narrative."""
    async with pool.connection() as conn, conn.transaction():
        last = await (
            await conn.execute(
                "SELECT * FROM sar_drafts WHERE case_id = %s ORDER BY version_no DESC LIMIT 1 "
                "FOR UPDATE",
                [case_id],
            )
        ).fetchone()
        if last is None:
            raise KeyError(case_id)
        if last["status"] == "approved":
            raise CaseStateError("the report is already approved")
        if last["source"] != "analyst":
            raise CaseStateError("an analyst must review and save the AI draft before approval")
        if role != "supervisor":
            raise CaseStateError("four-eyes rule: only a supervisor can approve the report")
        if reviewer == last["author"]:
            raise CaseStateError("four-eyes rule: the report must be approved by someone else")
        return await (
            await conn.execute(
                "UPDATE sar_drafts SET status = 'approved', approved_by = %s, approved_at = now() "
                "WHERE id = %s RETURNING *",
                [reviewer, last["id"]],
            )
        ).fetchone()


async def get_case(pool: AsyncConnectionPool, case_id: str) -> dict | None:
    async with pool.connection() as conn:
        case = await (
            await conn.execute("SELECT * FROM cases WHERE case_id = %s", [case_id])
        ).fetchone()
        if case is None:
            return None
        case["decisions"] = await (
            await conn.execute(
                "SELECT action, reason, reviewer, role, decided_at, applied_at FROM decisions "
                "WHERE case_id = %s ORDER BY decision_id",
                [case_id],
            )
        ).fetchall()
        return case


async def list_cases(pool: AsyncConnectionPool, status: str | None = None) -> list[dict]:
    sql = """
        SELECT case_id, alert_id, status, model, prompt_version, created_at, updated_at,
               alert->>'seed_bank' AS seed_bank, alert->>'seed_account' AS seed_account,
               draft->>'pattern_hypothesis' AS pattern,
               draft->>'recommended_action' AS recommended_action,
               draft->>'confidence' AS confidence,
               (verification->>'faithful')::boolean AS faithful,
               jsonb_array_length(warnings) AS n_warnings,
               jsonb_array_length(COALESCE(draft->'evidence', '[]'::jsonb)) AS n_evidence,
               (analysis->'risk'->>'score')::int AS risk_score,
               analysis->'risk'->>'band' AS risk_band
        FROM cases"""
    params: list = []
    if status:
        sql += " WHERE status = %s"
        params.append(status)
    sql += " ORDER BY created_at"
    async with pool.connection() as conn:
        return await (await conn.execute(sql, params)).fetchall()


async def record_decision(pool: AsyncConnectionPool, case_id: str, decision: Decision) -> None:
    """Record a human decision, enforcing who may decide what.

    A case ready for review takes an analyst outcome (close, escalate, request_more).
    An escalation then waits for a supervisor (four-eyes rule): only a reviewer with the
    supervisor role who is not the person who escalated may confirm or return it.
    """
    async with pool.connection() as conn, conn.transaction():
        row = await (
            await conn.execute("SELECT status FROM cases WHERE case_id = %s FOR UPDATE", [case_id])
        ).fetchone()
        if row is None:
            raise KeyError(case_id)
        status = row["status"]
        if status == "pending_review":
            if decision.action not in ANALYST_ACTIONS:
                raise CaseStateError(f"{decision.action} is not allowed on a case ready for review")
        elif status == "pending_approval":
            if decision.action not in SUPERVISOR_ACTIONS:
                raise CaseStateError(
                    "the case awaits a supervisor: confirm or return the escalation"
                )
            if decision.role != "supervisor":
                raise CaseStateError("four-eyes rule: only a supervisor can confirm an escalation")
            escalated_by = await (
                await conn.execute(
                    "SELECT reviewer FROM decisions WHERE case_id = %s AND action = 'escalate' "
                    "ORDER BY decision_id DESC LIMIT 1",
                    [case_id],
                )
            ).fetchone()
            if escalated_by and escalated_by["reviewer"] == decision.reviewer:
                raise CaseStateError(
                    "four-eyes rule: the escalation must be confirmed by a different person"
                )
        else:
            raise CaseStateError(f"case is {status}; it is not waiting for a decision")
        await conn.execute(
            "INSERT INTO decisions (case_id, action, reason, reviewer, role) "
            "VALUES (%s, %s, %s, %s, %s)",
            [case_id, decision.action, decision.reason, decision.reviewer, decision.role],
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
                "SELECT decision_id, action, reason, reviewer, role, decided_at FROM decisions "
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
                   verification = %s, case_graph = %s, analysis = %s,
                   provider = %s, model = %s, prompt_version = %s,
                   claimed_by = NULL, claimed_at = NULL, error = NULL, updated_at = now()
            WHERE case_id = %s
            """,
            [
                status,
                Jsonb(values.get("case")),
                Jsonb(values.get("warnings", [])),
                Jsonb(metrics),
                Jsonb(values.get("verification")),
                Jsonb(values.get("case_graph")),
                Jsonb(_analysis(values)),
                values.get("provider"),
                values.get("model"),
                values.get("prompt_version"),
                case_id,
            ],
        )


async def stats(pool: AsyncConnectionPool) -> dict:
    """Counts for the operations dashboard."""
    async with pool.connection() as conn:
        by_status = await (
            await conn.execute("SELECT status, count(*) AS n FROM cases GROUP BY status")
        ).fetchall()
        by_action = await (
            await conn.execute(
                "SELECT draft->>'recommended_action' AS action, count(*) AS n FROM cases "
                "WHERE draft IS NOT NULL GROUP BY 1"
            )
        ).fetchall()
        by_pattern = await (
            await conn.execute(
                "SELECT draft->>'pattern_hypothesis' AS pattern, count(*) AS n FROM cases "
                "WHERE draft IS NOT NULL GROUP BY 1"
            )
        ).fetchall()
        decisions = await (
            await conn.execute("SELECT action, count(*) AS n FROM decisions GROUP BY action")
        ).fetchall()
        verified = await (
            await conn.execute(
                "SELECT count(*) FILTER (WHERE (verification->>'faithful')::boolean) AS faithful, "
                "count(verification) AS checked FROM cases"
            )
        ).fetchone()
    return {
        "by_status": {r["status"]: r["n"] for r in by_status},
        "by_recommended_action": {r["action"]: r["n"] for r in by_action},
        "by_pattern": {r["pattern"]: r["n"] for r in by_pattern},
        "decisions": {r["action"]: r["n"] for r in decisions},
        "verification": verified,
    }


async def requeue_case(pool: AsyncConnectionPool, case_id: str) -> None:
    """Put a claimed case back in the queue (its worker lost the tool connection)."""
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE cases SET status = CASE WHEN run_phase = 'resume' THEN 'decision_recorded' "
            "ELSE 'queued' END, claimed_by = NULL, claimed_at = NULL, updated_at = now() "
            "WHERE case_id = %s AND status = 'running'",
            [case_id],
        )


async def retry_failed(pool: AsyncConnectionPool, case_id: str) -> None:
    """Queue a failed case again; it resumes from its last checkpoint."""
    async with pool.connection() as conn, conn.transaction():
        row = await (
            await conn.execute("SELECT status FROM cases WHERE case_id = %s FOR UPDATE", [case_id])
        ).fetchone()
        if row is None:
            raise KeyError(case_id)
        if row["status"] != "failed":
            raise CaseStateError(f"case is {row['status']}; only a failed review can be retried")
        await conn.execute(
            "UPDATE cases SET status = CASE WHEN run_phase = 'resume' THEN 'decision_recorded' "
            "ELSE 'queued' END, error = NULL, claimed_by = NULL, claimed_at = NULL, "
            "updated_at = now() WHERE case_id = %s",
            [case_id],
        )


async def mark_failed(pool: AsyncConnectionPool, case_id: str, error: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE cases SET status = 'failed', error = %s, claimed_by = NULL, "
            "claimed_at = NULL, updated_at = now() WHERE case_id = %s",
            [error[:4000], case_id],
        )
