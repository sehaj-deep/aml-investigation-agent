"""Sprint 1 Verify against real processes: API, worker, MCP server and Postgres.

Needs the Postgres container (docker compose up) and the Parquet build.
Kill-and-resume: a case paused for review survives a hard worker kill.
"""

from __future__ import annotations

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
        api_env = {**os.environ, **env, "API_PORT": str(port)}
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

    decision = {"action": "approve", "reason": "Consistent with fan-out.", "reviewer": "tester"}
    assert httpx.post(f"{api}/cases/{case_id}/decision", json=decision).status_code == 200
    worker = start_worker(stack["worker_env"])
    try:
        final = wait_status(api, case_id, "approved")
    finally:
        worker.terminate()
        worker.wait(timeout=30)
    assert [d["action"] for d in final["decisions"]] == ["approve"]
    assert final["draft"] == paused["draft"]


def test_api_rules(stack):
    api = stack["api"]
    paths = httpx.get(f"{api}/openapi.json").json()["paths"]
    assert not any("final" in p for p in paths), "no endpoint may finalize a case"

    case_id = httpx.post(f"{api}/cases", json={"alert_id": "dev-0003"}).json()["case_id"]
    decision = {"action": "approve", "reason": "Too early.", "reviewer": "tester"}
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
