"""Sprint 1 Verify against real processes: API, worker, MCP server and Postgres.

Needs the Postgres container (docker compose up) and the Parquet build.
Kill-and-resume: a case paused for review survives a hard worker kill.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator

import httpx
import psycopg
import pytest

from aml_agent import config, store
from tests.helpers import free_port, mcp_http_server, wait_for_port

pytestmark = [pytest.mark.docker, pytest.mark.data]


TEST_DB = "aml_test"


def _prepare_test_db() -> bool:
    """Create a separate database so the Docker worker never claims test cases."""
    try:
        with psycopg.connect(store.database_url(), connect_timeout=3, autocommit=True) as c:
            exists = c.execute("SELECT 1 FROM pg_database WHERE datname = %s", [TEST_DB]).fetchone()
            if not exists:
                c.execute(f"CREATE DATABASE {TEST_DB}")
        return True
    except psycopg.Error:
        return False


QUEUE_SAMPLE = 3


@pytest.fixture(scope="module")
def stack(tmp_path_factory) -> Iterator[dict]:
    if not _prepare_test_db():
        pytest.skip("Postgres is not running (docker compose up -d)")
    # A small monitoring queue: the first alerts of the real one (scripts/train_detection.py).
    queue_dir = tmp_path_factory.mktemp("alert_queue")
    real = config.alert_queue_dir() / "alerts.jsonl"
    if real.exists():
        lines = real.read_text(encoding="utf-8").splitlines()[:QUEUE_SAMPLE]
        (queue_dir / "alerts.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    env = {
        "LLM_PROVIDER": "scripted",
        "LLM_SCRIPT_POLICY": "basic",
        "POSTGRES_DB": TEST_DB,
        "ALERT_QUEUE_DIR": str(queue_dir),
    }
    with mcp_http_server() as mcp_url:
        port = free_port()
        api_env = {**os.environ, **env, "API_PORT": str(port), "MCP_URL": mcp_url}
        api = subprocess.Popen(
            [sys.executable, "-m", "aml_agent.api"],
            env=api_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_for_port(port)
            yield {
                "api": f"http://127.0.0.1:{port}",
                "worker_env": {**os.environ, **env, "MCP_URL": mcp_url},
            }
        finally:
            api.terminate()
            api.wait(timeout=30)


def start_worker(env: dict) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "aml_agent.worker"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_status(api: str, case_id: str, wanted: str, timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        case = httpx.get(f"{api}/cases/{case_id}").json()
        if case["status"] == wanted:
            return case
        if case["status"] == "failed":
            raise AssertionError(f"case failed: {case['error']}")
        time.sleep(0.5)
    raise TimeoutError(f"case {case_id} never reached {wanted}")


def test_kill_worker_while_paused_then_resume(stack):
    api = stack["api"]
    case_id = httpx.post(f"{api}/cases", json={"alert_id": "dev-0002"}).json()["case_id"]
    worker = start_worker(stack["worker_env"])
    try:
        paused = wait_status(api, case_id, "pending_review")
    finally:
        worker.kill()  # hard kill, no cleanup
        worker.wait(timeout=30)
    assert paused["draft"]["evidence"]

    decide = f"{api}/cases/{case_id}/decision"
    escalate = {"action": "escalate", "reason": "Consistent with fan-out.", "reviewer": "ana"}
    assert httpx.post(decide, json=escalate).status_code == 200
    worker = start_worker(stack["worker_env"])
    try:
        wait_status(api, case_id, "pending_approval")
        # Four-eyes rule, enforced by the server: not an analyst, not the escalator.
        confirm = {
            "action": "confirm_escalation",
            "reason": "Agreed, file the report.",
            "reviewer": "sam",
            "role": "supervisor",
        }
        assert httpx.post(decide, json={**confirm, "role": "analyst"}).status_code == 409
        assert httpx.post(decide, json={**confirm, "reviewer": "ana"}).status_code == 409
        assert httpx.post(decide, json={**escalate, "reviewer": "sam"}).status_code == 409
        assert httpx.post(decide, json=confirm).status_code == 200
        final = wait_status(api, case_id, "escalated")
    finally:
        worker.terminate()
        worker.wait(timeout=30)
    assert [d["action"] for d in final["decisions"]] == ["escalate", "confirm_escalation"]
    assert [d["role"] for d in final["decisions"]] == ["analyst", "supervisor"]
    assert final["draft"] == paused["draft"]


def test_api_rules(stack):
    api = stack["api"]
    paths = httpx.get(f"{api}/openapi.json").json()["paths"]
    assert not any("final" in p for p in paths), "no endpoint may finalize a case"

    case_id = httpx.post(f"{api}/cases", json={"alert_id": "dev-0003"}).json()["case_id"]
    decision = {"action": "close", "reason": "Too early.", "reviewer": "tester"}
    r = httpx.post(f"{api}/cases/{case_id}/decision", json=decision)
    assert r.status_code == 409  # queued, not pending_review

    bad = {"action": "finalize", "reason": "x" * 5, "reviewer": "tester"}
    assert httpx.post(f"{api}/cases/{case_id}/decision", json=bad).status_code == 422
    assert httpx.post(f"{api}/cases", json={"alert_id": "dev-9999"}).status_code == 404
    both = {"alert_id": "dev-0001", "alert": {"alert_id": "x"}}
    assert httpx.post(f"{api}/cases", json=both).status_code == 422
    assert httpx.get(f"{api}/cases/nope").status_code == 404


def test_alert_queue_pages_and_opens_one_case_per_alert(stack):
    api = stack["api"]
    page = httpx.get(f"{api}/alerts", params={"limit": 2}).json()
    if page["total"] == 0:
        pytest.skip("no monitoring queue; run scripts/train_detection.py")
    assert len(page["items"]) == min(2, page["total"])
    ranks = [a["rank"] for a in page["items"]]
    assert ranks == sorted(ranks)
    labels = {"label", "is_laundering", "pattern_blocks", "true_triggers"}
    assert not labels & set(page["items"][0])
    alert_id = page["items"][0]["alert_id"]
    first = httpx.post(f"{api}/alerts/{alert_id}/open").json()
    again = httpx.post(f"{api}/alerts/{alert_id}/open").json()
    assert again == {"case_id": first["case_id"], "created": False}
    alert = httpx.get(f"{api}/alerts/{alert_id}").json()
    assert alert["case_id"] == first["case_id"] and alert["status"] != "new"
    assert not labels & set(alert["alert"])
    case = httpx.get(f"{api}/cases/{first['case_id']}").json()
    assert case["alert"]["trigger_tx_ids"] == alert["alert"]["trigger_tx_ids"]
    summary = httpx.get(f"{api}/alerts/summary").json()
    assert summary["total"] >= page["total"]
    assert httpx.post(f"{api}/alerts/ALR-99999999/open").status_code == 404
    assert httpx.get(f"{api}/alerts", params={"limit": 500}).status_code == 422


def test_stats_work(stack):
    api = stack["api"]
    stats = httpx.get(f"{api}/stats").json()
    assert set(stats) >= {"by_status", "by_recommended_action", "decisions", "verification"}


def test_copilot_answers_and_keeps_history(stack):
    api = stack["api"]
    case_id = httpx.post(f"{api}/cases", json={"alert_id": "dev-0004"}).json()["case_id"]
    url = f"{api}/cases/{case_id}/copilot"
    assert httpx.post(url, json={"question": "Too early?"}).status_code == 409
    worker = start_worker(stack["worker_env"])
    try:
        wait_status(api, case_id, "pending_review")
    finally:
        worker.terminate()
        worker.wait(timeout=30)
    events = []
    with httpx.stream("POST", url, json={"question": "What did the subject send?"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    assert [e["type"] for e in events] == ["tool", "answer"]
    answer = events[-1]
    assert answer["answer"].startswith("Scripted copilot answer")
    assert answer["unverified"] == []
    history = httpx.get(url).json()
    assert history["used"] == 1 and history["answers"][0]["id"] == answer["id"]
    audit = httpx.get(f"{api}/cases/{case_id}/audit").json()
    types = [e["event_type"] for e in audit["events"]]
    assert "copilot_question" in types and "copilot_answer" in types
    assert httpx.post(url, json={"question": "x"}).status_code == 422


def test_failed_review_can_be_retried(stack):
    api = stack["api"]
    case_id = httpx.post(f"{api}/cases", json={"alert_id": "dev-0005"}).json()["case_id"]
    retry = f"{api}/cases/{case_id}/retry"
    assert httpx.post(retry).status_code == 409  # queued, not failed
    with psycopg.connect(store.database_url().rsplit("/", 1)[0] + f"/{TEST_DB}") as c:
        c.execute(
            "UPDATE cases SET status = 'failed', error = 'McpError: Session terminated' "
            "WHERE case_id = %s",
            [case_id],
        )
    assert httpx.post(retry).status_code == 200
    case = httpx.get(f"{api}/cases/{case_id}").json()
    assert case["status"] == "queued" and case["error"] is None
    assert httpx.post(f"{api}/cases/nope/retry").status_code == 404


def test_sar_draft_review_and_four_eyes_approval(stack):
    api = stack["api"]
    case_id = httpx.post(f"{api}/cases", json={"alert_id": "dev-0006"}).json()["case_id"]
    base = f"{api}/cases/{case_id}"
    assert httpx.post(f"{base}/sar/draft").status_code == 409  # not escalated yet
    worker = start_worker(stack["worker_env"])
    try:
        wait_status(api, case_id, "pending_review")
        escalate = {"action": "escalate", "reason": "Rapid dispersion.", "reviewer": "ana"}
        assert httpx.post(f"{base}/decision", json=escalate).status_code == 200
        wait_status(api, case_id, "pending_approval")
        confirm = {
            "action": "confirm_escalation",
            "reason": "Agreed.",
            "reviewer": "sam",
            "role": "supervisor",
        }
        assert httpx.post(f"{base}/decision", json=confirm).status_code == 200
        wait_status(api, case_id, "escalated")
    finally:
        worker.terminate()
        worker.wait(timeout=30)

    drafted = httpx.post(f"{base}/sar/draft", timeout=60)
    assert drafted.status_code == 200
    v1 = drafted.json()
    assert v1["version_no"] == 1 and v1["source"] == "ai" and v1["warnings"] == []
    assert v1["facts"]["transactions"] and v1["facts"]["filing_due"]
    supervisor = {"reviewer": "sam", "role": "supervisor"}
    # An unedited AI draft cannot be approved: an analyst reviews and saves it first.
    assert httpx.post(f"{base}/sar/approve", json=supervisor).status_code == 409
    edit = {"sections": v1["sections"], "author": "ana", "role": "analyst"}
    edit["sections"]["conclusion"] = "Reviewed by the analyst; the account is referred for filing."
    v2 = httpx.put(f"{base}/sar", json=edit).json()
    assert v2["version_no"] == 2 and v2["source"] == "analyst"
    assert (
        httpx.post(f"{base}/sar/approve", json={**supervisor, "reviewer": "ana"}).status_code == 409
    )
    assert (
        httpx.post(f"{base}/sar/approve", json={**supervisor, "role": "analyst"}).status_code == 409
    )
    approved = httpx.post(f"{base}/sar/approve", json=supervisor)
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert httpx.put(f"{base}/sar", json=edit).status_code == 409  # approved is final
    doc = httpx.get(f"{base}/sar/export")
    assert doc.headers["content-type"].startswith("text/markdown")
    assert "Reviewed by the analyst" in doc.text and "approved by sam" in doc.text
    state = httpx.get(f"{base}/sar").json()
    assert state["versions"] == 2 and state["ai_drafts"] == 1
    audit = [e["event_type"] for e in httpx.get(f"{base}/audit").json()["events"]]
    assert {"sar_drafted", "sar_edited", "sar_approved"} <= set(audit)
