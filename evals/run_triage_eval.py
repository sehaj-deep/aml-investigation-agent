"""Final evaluation of the AI analyst on monitoring alerts (scorecard part B).

    python evals/run_triage_eval.py                          live model; needs tag eval-freeze
    python evals/run_triage_eval.py --provider scripted --limit 3 --allow-unfrozen
                                                             harness check, no quota

Runs the AI review end to end (up to the analyst's decision) on the frozen evaluation
alerts in evals/alerts/detection/ (a seeded sample of the monitoring queue: 50 alerts per
priority band, labels kept apart). The AI reaches data only through the MCP tool server,
which this script starts locally; labels are read only to score.

Reported:
- triage: for real laundering, the share escalated, sent back for more information and
  closed (missed); for false alarms, the share closed, escalated and sent back;
- the same by priority band;
- faithfulness: cases whose cited transactions all verified, guidance quotes kept and
  rejected, valid drafts;
- cost and speed: tokens and seconds per case, tool calls.

Each finished case is appended to a progress file at once, so an interrupted run resumes
without paying twice (--resume <file>). The evaluation set is refused unless the freeze
tag exists, so nothing is tuned on its results.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from aml_agent.agent.graph import compile_graph  # noqa: E402
from aml_agent.agent.prompts import PROMPT_VERSION  # noqa: E402
from aml_agent.alerts.models import Alert  # noqa: E402
from aml_agent.data.views import connect  # noqa: E402
from aml_agent.guidance.search import ollama_url  # noqa: E402
from aml_agent.llm.base import get_provider  # noqa: E402
from aml_agent.metrics import case_metrics  # noqa: E402
from aml_agent.tools.client import connect_graph  # noqa: E402
from aml_agent.verify.citations import CitationVerifier  # noqa: E402

FREEZE_TAG = "eval-freeze"
ALERTS = ROOT / "evals" / "alerts" / "detection"
RUNS = ROOT / "evals" / "runs" / "triage"
BANDS = ("high", "medium", "low")
# Quota share per 100,000 tokens, measured on the owner's account (scorecard part C).
QUOTA_PER_100K = 0.56


def freeze_tag_exists() -> bool:
    out = subprocess.run(
        ["git", "tag", "--list", FREEZE_TAG], cwd=ROOT, capture_output=True, text=True
    )
    return bool(out.stdout.strip())


def git_commit() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    )
    return out.stdout.strip()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_tool_server() -> tuple[subprocess.Popen, str]:
    """The read-only MCP tool server, local, over HTTP."""
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "aml_agent.tools.mcp_server", "--http"],
        env={**os.environ, "MCP_HOST": "127.0.0.1", "MCP_PORT": str(port)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 90
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return proc, f"http://127.0.0.1:{port}/mcp"
        time.sleep(0.3)
    proc.terminate()
    raise SystemExit("the MCP tool server did not start")


def load() -> tuple[list[Alert], dict[str, dict]]:
    alerts = [
        Alert.model_validate_json(line)
        for line in (ALERTS / "alerts.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    truth = {
        t["alert_id"]: t
        for t in map(
            json.loads, (ALERTS / "ground_truth.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    return alerts, truth


async def run(alerts: list[Alert], truth: dict, progress: Path, done: set[str]) -> None:
    con = connect()
    verifier = CitationVerifier(con)
    provider = get_provider()
    async with connect_graph() as client:
        app = compile_graph(provider, client, InMemorySaver(), verifier=verifier)
        for n, alert in enumerate(alerts, start=1):
            if alert.alert_id in done:
                continue
            cfg = {"configurable": {"thread_id": alert.alert_id}}
            start = time.perf_counter()
            error = None
            try:
                await app.ainvoke(
                    {"case_id": alert.alert_id, "alert": alert.model_dump(mode="json")}, cfg
                )
            except Exception as exc:  # a failed case is a result, not a crash
                error = f"{type(exc).__name__}: {exc}"
            seconds = round(time.perf_counter() - start, 1)
            values = (await app.aget_state(cfg)).values
            case = values.get("case") or {}
            ver = values.get("verification") or {}
            guidance = values.get("guidance") or []
            warnings = values.get("warnings") or []
            t = truth[alert.alert_id]
            row = {
                "alert_id": alert.alert_id,
                "priority": alert.priority,
                "label": t["label"],
                "pattern_linked": bool(t["pattern_blocks"]),
                "action": case.get("recommended_action"),
                "confidence": case.get("confidence"),
                "pattern": case.get("pattern_hypothesis"),
                "faithful": ver.get("faithful"),
                "grounded": ver.get("grounded"),
                "evidence_rows": len(case.get("evidence", [])),
                "guidance_found": len(guidance),
                "guidance_kept": len(case.get("guidance_citations", [])),
                "guidance_rejected": sum(1 for w in warnings if w.startswith("GUIDANCE_")),
                "draft_invalid": any(w.startswith("MODEL_OUTPUT_INVALID") for w in warnings),
                "seconds": seconds,
                "error": error,
                **(case_metrics(values) if values else {}),
            }
            with progress.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, default=str) + "\n")
            print(
                f"[{n}/{len(alerts)}] {alert.alert_id} {alert.priority:6} {t['label']:8} -> "
                f"{row['action']!s:15} tools={row.get('tool_calls')} "
                f"tokens={row.get('input_tokens', 0) + row.get('output_tokens', 0)} {seconds}s",
                flush=True,
            )


def share(items: list[dict], cond) -> float | None:
    return round(sum(1 for r in items if cond(r)) / len(items), 4) if items else None


def triage(rows: list[dict]) -> dict:
    real = [r for r in rows if r["label"] == "positive"]
    false = [r for r in rows if r["label"] == "benign"]

    def actions(items: list[dict]) -> dict:
        return {
            a: share(items, lambda r, a=a: r["action"] == a)
            for a in ("escalate", "needs_more_info", "close")
        }

    return {
        "alerts": len(rows),
        "laundering": {"n": len(real), **actions(real)},
        "false_alarms": {"n": len(false), **actions(false)},
    }


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r["error"]]
    tokens = [r.get("input_tokens", 0) + r.get("output_tokens", 0) for r in ok]
    seconds = sorted(r["seconds"] for r in ok)
    cited = [r for r in ok if r["guidance_kept"] + r["guidance_rejected"] > 0]
    return {
        "cases": len(rows),
        "errors": len(rows) - len(ok),
        "triage": triage(ok),
        "by_priority": {b: triage([r for r in ok if r["priority"] == b]) for b in BANDS},
        "faithfulness": {
            "all_citations_verified": share(ok, lambda r: r["faithful"] is True),
            "valid_drafts": share(ok, lambda r: not r["draft_invalid"]),
            "cases_citing_guidance": share(ok, lambda r: r["guidance_kept"] > 0),
            "guidance_quotes_kept": sum(r["guidance_kept"] for r in ok),
            "guidance_quotes_rejected": sum(r["guidance_rejected"] for r in ok),
            "guidance_quote_precision": round(
                sum(r["guidance_kept"] for r in cited)
                / max(sum(r["guidance_kept"] + r["guidance_rejected"] for r in cited), 1),
                4,
            ),
        },
        "cost": {
            "tokens_total": sum(tokens),
            "tokens_median": statistics.median(tokens) if tokens else None,
            "quota_share_estimate_pct": round(sum(tokens) / 100_000 * QUOTA_PER_100K, 2),
            "seconds_median": statistics.median(seconds) if seconds else None,
            "seconds_p95": seconds[min(len(seconds) - 1, int(0.95 * len(seconds)))]
            if seconds
            else None,
            "tool_calls_median": statistics.median(r.get("tool_calls", 0) for r in ok)
            if ok
            else None,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default=os.environ.get("LLM_PROVIDER", "ollama"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", type=Path, default=None, help="progress file to continue")
    parser.add_argument("--allow-unfrozen", action="store_true", help="harness checks only")
    args = parser.parse_args()
    if not (freeze_tag_exists() or args.allow_unfrozen):
        raise SystemExit(f"refusing the evaluation set: tag {FREEZE_TAG!r} does not exist yet")
    os.environ["LLM_PROVIDER"] = args.provider
    os.environ["OLLAMA_BASE_URL"] = ollama_url()  # this script runs on the host
    alerts, truth = load()
    if args.limit:
        alerts = alerts[: args.limit]
    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    progress = args.resume or RUNS / f"progress-{args.provider}-{stamp}.jsonl"
    done = (
        {
            json.loads(line)["alert_id"]
            for line in progress.read_text(encoding="utf-8").splitlines()
            if line
        }
        if progress.exists()
        else set()
    )
    print(f"{len(alerts)} alerts, {len(done)} already done; progress: {progress}", flush=True)
    server, url = start_tool_server()
    os.environ["MCP_URL"] = url
    try:
        asyncio.run(run(alerts, truth, progress, done))
    finally:
        server.terminate()
        server.wait(timeout=30)
    rows = [json.loads(line) for line in progress.read_text(encoding="utf-8").splitlines() if line]
    rows = [r for r in rows if r["alert_id"] in {a.alert_id for a in alerts}]
    provider = get_provider()
    record = {
        "created_utc": stamp,
        "alert_set": "detection evaluation sample (evals/alerts/detection)",
        "frozen": freeze_tag_exists(),
        "commit": git_commit(),
        "provider": provider.provider,
        "model": provider.model,
        "prompt_version": PROMPT_VERSION,
        "note": "scripted: harness check only, not a model result"
        if provider.provider == "scripted"
        else "live run, one pass, uncached",
        "summary": summarize(rows),
        "cases": rows,
    }
    out = RUNS / f"triage-{provider.provider}-{stamp}.json"
    out.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(record["summary"], indent=1))
    print(f"written {out}")


if __name__ == "__main__":
    main()
