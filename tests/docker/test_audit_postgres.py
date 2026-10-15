"""Sprint 2 Verify against Postgres: append-only audit log, rebuild from the log
alone matches the live run, traces stored."""

from __future__ import annotations

import time

import httpx
import psycopg
import pytest
from langgraph.checkpoint.postgres import PostgresSaver

from aml_agent import store
from aml_agent.audit import reconstruct, verify_chain
from tests.docker.test_worker_api import (
    TEST_DB,
    stack,  # noqa: F401  (fixture)
    start_worker,
    wait_status,
)

pytestmark = [pytest.mark.docker, pytest.mark.data]


def _test_db_url() -> str:
    return store.database_url().rsplit("/", 1)[0] + f"/{TEST_DB}"


@pytest.fixture(scope="module")
def finished_case(stack):  # noqa: F811
    api = stack["api"]
    case_id = httpx.post(f"{api}/cases", json={"alert_id": "dev-0005"}).json()["case_id"]
    worker = start_worker(stack["worker_env"])
    try:
        wait_status(api, case_id, "pending_review")
        more = {"action": "request_more", "reason": "Check inbound flows.", "reviewer": "tester"}
        httpx.post(f"{api}/cases/{case_id}/decision", json=more).raise_for_status()
        wait_status(api, case_id, "pending_review")
        time.sleep(1)
        close = {"action": "close", "reason": "Ordinary activity.", "reviewer": "tester"}
        httpx.post(f"{api}/cases/{case_id}/decision", json=close).raise_for_status()
        wait_status(api, case_id, "closed")
    finally:
        worker.terminate()
        worker.wait(timeout=30)
    return case_id


def test_rebuild_from_audit_log_matches_live_run(stack, finished_case):  # noqa: F811
    body = httpx.get(f"{stack['api']}/cases/{finished_case}/audit").json()
    events = body["events"]
    assert body["chain_valid"] is True and verify_chain(events)
    rebuilt = reconstruct(events)
    with PostgresSaver.from_conn_string(_test_db_url()) as saver:
        tup = saver.get_tuple({"configurable": {"thread_id": finished_case}})
    live = {k: v for k, v in tup.checkpoint["channel_values"].items() if not k.startswith("_")}
    live = {k: v for k, v in live.items() if not k.startswith("branch:")}
    assert rebuilt == live
    assert rebuilt["status"] == "closed"
    types = [e["event_type"] for e in events]
    assert types[0] == "case_created"
    assert types.count("decision_recorded") == 2 and types.count("decision_applied") == 2
    lines = httpx.get(f"{stack['api']}/cases/{finished_case}/timeline").json()["lines"]
    assert len(lines) == len(events)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit_log SET actor = 'x' WHERE case_id = %s",
        "DELETE FROM audit_log WHERE case_id = %s",
    ],
)
def test_update_and_delete_are_blocked(finished_case, sql):
    with psycopg.connect(_test_db_url(), autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            conn.execute(sql, [finished_case])
        n = conn.execute(
            "SELECT count(*) FROM audit_log WHERE case_id = %s", [finished_case]
        ).fetchone()[0]
    assert n > 0


def test_truncate_is_blocked(finished_case):
    with (
        psycopg.connect(_test_db_url(), autocommit=True) as conn,
        pytest.raises(psycopg.errors.RaiseException, match="append-only"),
    ):
        conn.execute("TRUNCATE audit_log")


def test_traces_stored_in_postgres(finished_case):
    deadline = time.time() + 20
    while time.time() < deadline:
        with psycopg.connect(_test_db_url(), autocommit=True) as conn:
            names = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM traces WHERE trace_id IN "
                    "(SELECT trace_id FROM traces WHERE case_id = %s)",
                    [finished_case],
                ).fetchall()
            }
        if {"case.run", "node.agent", "model.chat"} <= names:
            break
        time.sleep(1)
    assert {"case.run", "node.triage", "node.agent", "model.chat", "node.verify"} <= names
    assert any(n.startswith("tool.") for n in names)
