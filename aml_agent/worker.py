"""Agent worker: claims cases from Postgres and runs the workflow (agent-worker service).

python -m aml_agent.worker            run forever
python -m aml_agent.worker --once     process until the queue is empty, then exit

If the connection to the MCP tool server drops (for example when mcp-graph restarts),
the case in progress goes back to the queue, the worker reconnects and carries on: a
lost connection is not a failed review. The case resumes from its last checkpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from mcp.shared.exceptions import McpError
from opentelemetry import trace

from aml_agent import store
from aml_agent.agent.graph import compile_graph
from aml_agent.audit import PostgresAudit
from aml_agent.llm.base import get_provider
from aml_agent.metrics import case_metrics
from aml_agent.tools.client import connect_graph
from aml_agent.tracing import setup_tracing
from aml_agent.verify.citations import CitationVerifier

log = logging.getLogger("aml_agent.worker")

RECONNECT_DELAYS = (1, 2, 5, 10, 30)  # seconds, then 30 s between attempts


class ToolConnectionLost(RuntimeError):
    """The MCP session to the tool server is gone; reconnect and retry the case."""


def is_connection_lost(exc: BaseException) -> bool:
    """A protocol or transport failure of the tool connection, not a case failure.

    McpError is raised by the MCP session itself (tool errors come back as results, not
    exceptions), so any McpError means the session is unusable.
    """
    if isinstance(exc, ToolConnectionLost | McpError | ConnectionError):
        return True
    transport = {"ClosedResourceError", "BrokenResourceError", "EndOfStream"}  # anyio streams
    transport |= {"ConnectError", "ReadError", "RemoteProtocolError"}  # httpx
    if type(exc).__name__ in transport:
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(is_connection_lost(e) for e in exc.exceptions)
    cause = exc.__cause__ or exc.__context__
    return cause is not None and cause is not exc and is_connection_lost(cause)


async def process(app: Any, pool, audit: PostgresAudit, job: dict) -> str:
    case_id = job["case_id"]
    cfg = {"configurable": {"thread_id": case_id}}
    snapshot = await app.aget_state(cfg)
    if job["run_phase"] == "resume":
        decision = await store.next_decision(pool, case_id)
        if decision is None:
            raise RuntimeError("resume requested but no unapplied decision exists")
        payload = {k: decision[k] for k in ("action", "reason", "reviewer", "role")}
        payload["decided_at"] = decision["decided_at"].isoformat()
        await app.ainvoke(Command(resume=payload), cfg)
        await store.mark_decision_applied(pool, decision["decision_id"])
        await audit.emit(case_id, "decision_applied", payload, actor="worker")
    elif snapshot.values:
        # Started before (a worker died mid-run): continue from the last checkpoint.
        if snapshot.next and snapshot.next not in (("human_review",), ("supervisor_review",)):
            await app.ainvoke(None, cfg)
    else:
        start = {"case_id": case_id, "alert": job["alert"]}
        async for update in app.astream(start, cfg, stream_mode="updates"):
            if "triage" in update:
                # The code-built case file is ready in seconds: show it while the AI works.
                await store.save_case_file(pool, case_id, (await app.aget_state(cfg)).values)

    snapshot = await app.aget_state(cfg)
    values = snapshot.values
    if snapshot.next == ("human_review",):
        status = "pending_review"
    elif snapshot.next == ("supervisor_review",):
        status = "pending_approval"
    elif values.get("status") in store.FINAL_STATUSES:
        status = values["status"]
    else:
        raise RuntimeError(f"unexpected workflow state: next={snapshot.next}")
    await store.save_progress(pool, case_id, status, values, case_metrics(values))
    await audit.emit(case_id, "status", {"status": status}, actor="worker")
    return status


async def run(once: bool = False, poll_seconds: float = 1.0) -> None:
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    provider = get_provider()
    url = store.database_url()
    tracer_provider = setup_tracing(url, "agent-worker")
    tracer = trace.get_tracer("aml_agent.worker")
    verifier = CitationVerifier()
    async with (
        store.make_pool(url) as pool,
        AsyncPostgresSaver.from_conn_string(url) as saver,
    ):
        await saver.setup()
        await store.init_schema(pool)
        audit = PostgresAudit(pool)
        await audit.init_schema()
        attempt = 0
        while True:
            try:
                async with connect_graph() as client:
                    app = compile_graph(provider, client, saver, audit=audit, verifier=verifier)
                    await client.tool_specs()  # fail fast if the tool server is not there
                    log.info(
                        "worker %s ready (%s %s)", worker_id, provider.provider, provider.model
                    )
                    attempt = 0
                    if await _serve(
                        app, pool, audit, worker_id, tracer, tracer_provider, once, poll_seconds
                    ):
                        return
            except BaseException as exc:
                if not is_connection_lost(exc):
                    raise
                delay = RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)]
                attempt += 1
                log.warning("tool server connection lost (%s); reconnecting in %s s", exc, delay)
                await asyncio.sleep(delay)


async def _serve(app, pool, audit, worker_id, tracer, tracer_provider, once, poll_seconds) -> bool:
    """Claim and run cases until the queue is empty (with --once). Returns True when done;
    raises ToolConnectionLost when the tool connection drops (the case is requeued)."""
    while True:
        job = await store.claim_next(pool, worker_id)
        if job is None:
            if once:
                return True
            await asyncio.sleep(poll_seconds)
            continue
        try:
            with tracer.start_as_current_span("case.run") as span:
                span.set_attribute("case_id", job["case_id"])
                span.set_attribute("run_phase", job["run_phase"])
                status = await process(app, pool, audit, job)
            log.info("case %s -> %s", job["case_id"], status)
        except Exception as exc:  # one bad case must not stop the worker
            if is_connection_lost(exc):
                await store.requeue_case(pool, job["case_id"])
                await audit.emit(
                    job["case_id"],
                    "status",
                    {"status": "requeued", "reason": "tool server connection lost"},
                    actor="worker",
                )
                raise ToolConnectionLost(str(exc)) from exc
            log.exception("case %s failed", job["case_id"])
            error = f"{type(exc).__name__}: {exc}"
            await store.mark_failed(pool, job["case_id"], error)
            await audit.emit(
                job["case_id"], "status", {"status": "failed", "error": error}, actor="worker"
            )
        finally:
            tracer_provider.force_flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if os.name == "nt":
        # psycopg async needs the selector event loop on Windows.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(once=args.once))


if __name__ == "__main__":
    main()
