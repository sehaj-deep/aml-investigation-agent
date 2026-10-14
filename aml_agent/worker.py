"""Agent worker: claims cases from Postgres and runs the workflow (agent-worker service).

python -m aml_agent.worker            run forever
python -m aml_agent.worker --once     process until the queue is empty, then exit
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

from aml_agent import store
from aml_agent.agent.graph import compile_graph
from aml_agent.llm.base import get_provider
from aml_agent.metrics import case_metrics
from aml_agent.tools.client import connect_graph

log = logging.getLogger("aml_agent.worker")


async def process(app: Any, pool, job: dict) -> str:
    case_id = job["case_id"]
    cfg = {"configurable": {"thread_id": case_id}}
    snapshot = await app.aget_state(cfg)
    if job["run_phase"] == "resume":
        decision = await store.next_decision(pool, case_id)
        if decision is None:
            raise RuntimeError("resume requested but no unapplied decision exists")
        payload = {k: decision[k] for k in ("action", "reason", "reviewer")}
        payload["decided_at"] = decision["decided_at"].isoformat()
        await app.ainvoke(Command(resume=payload), cfg)
        await store.mark_decision_applied(pool, decision["decision_id"])
    elif snapshot.values:
        # Started before (a worker died mid-run): continue from the last checkpoint.
        if snapshot.next and snapshot.next != ("human_review",):
            await app.ainvoke(None, cfg)
    else:
        await app.ainvoke({"case_id": case_id, "alert": job["alert"]}, cfg)

    snapshot = await app.aget_state(cfg)
    values = snapshot.values
    if snapshot.next == ("human_review",):
        status = "pending_review"
    elif values.get("status") in store.FINAL_STATUSES:
        status = values["status"]
    else:
        raise RuntimeError(f"unexpected workflow state: next={snapshot.next}")
    await store.save_progress(pool, case_id, status, values, case_metrics(values))
    return status


async def run(once: bool = False, poll_seconds: float = 1.0) -> None:
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    provider = get_provider()
    url = store.database_url()
    async with (
        store.make_pool(url) as pool,
        AsyncPostgresSaver.from_conn_string(url) as saver,
        connect_graph() as client,
    ):
        await saver.setup()
        await store.init_schema(pool)
        app = compile_graph(provider, client, saver)
        log.info("worker %s ready (%s %s)", worker_id, provider.provider, provider.model)
        while True:
            job = await store.claim_next(pool, worker_id)
            if job is None:
                if once:
                    return
                await asyncio.sleep(poll_seconds)
                continue
            try:
                status = await process(app, pool, job)
                log.info("case %s -> %s", job["case_id"], status)
            except Exception as exc:  # one bad case must not stop the worker
                log.exception("case %s failed", job["case_id"])
                await store.mark_failed(pool, job["case_id"], f"{type(exc).__name__}: {exc}")


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
