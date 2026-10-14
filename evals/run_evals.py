"""Evaluation harness: run an alert set end to end (up to the approval pause) and
report the section 11 metrics that exist so far.

    python evals/run_evals.py --set dev                     (live model from .env)
    python evals/run_evals.py --set dev --provider scripted (harness check only)

Per case: citation faithfulness and grounding (verifier), evidence coverage of the
true pattern block, pattern accuracy, recommended action. Aggregates are reported
overall and split by whether the alert's block runs past 2022/09/10 (PRD section
10: those rows are excluded from headline numbers and reported separately).

The evaluation set is refused unless the freeze tag exists (PRD section 9).
Results go to evals/runs/<set>/; scripted runs are labeled as harness checks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from aml_agent.agent.graph import compile_graph
from aml_agent.agent.prompts import PROMPT_VERSION
from aml_agent.alerts.io import read_alerts, read_truth
from aml_agent.data.views import connect
from aml_agent.llm.base import get_provider
from aml_agent.metrics import case_metrics
from aml_agent.tools.client import connect_graph
from aml_agent.verify.citations import CitationVerifier

ROOT = Path(__file__).resolve().parents[1]
FREEZE_TAG = "eval-freeze"
PATTERN_NAMES = {
    "FAN-OUT": "fan-out",
    "FAN-IN": "fan-in",
    "CYCLE": "cycle",
    "GATHER-SCATTER": "gather-scatter",
    "SCATTER-GATHER": "scatter-gather",
    "BIPARTITE": "bipartite",
    "STACK": "stack",
    "RANDOM": "random",
}


def freeze_tag_exists() -> bool:
    out = subprocess.run(
        ["git", "tag", "--list", FREEZE_TAG], cwd=ROOT, capture_output=True, text=True
    )
    return bool(out.stdout.strip())


def block_tx_ids(con, block_id: int) -> set[int]:
    rows = con.execute(
        "SELECT tx_id FROM pattern_transactions WHERE block_id = ?", [block_id]
    ).fetchall()
    return {r[0] for r in rows}


async def run_set(name: str, limit: int | None) -> list[dict]:
    alerts = {a.alert_id: a for a in read_alerts(name)}
    truth = read_truth(name)[:limit] if limit else read_truth(name)
    con = connect()
    verifier = CitationVerifier(con)
    provider = get_provider()
    rows = []
    async with connect_graph() as client:
        app = compile_graph(provider, client, InMemorySaver(), verifier=verifier)
        for t in truth:
            alert = alerts[t.alert_id]
            cfg = {"configurable": {"thread_id": t.alert_id}}
            start = time.perf_counter()
            error = None
            try:
                await app.ainvoke(
                    {"case_id": t.alert_id, "alert": alert.model_dump(mode="json")}, cfg
                )
            except Exception as exc:  # a failed case is a result, not a crash
                error = f"{type(exc).__name__}: {exc}"
            wall_ms = (time.perf_counter() - start) * 1000
            values = (await app.aget_state(cfg)).values
            case = values.get("case") or {}
            ver = values.get("verification") or {}
            evidence_ids = {e["tx_id"] for e in case.get("evidence", [])}
            coverage = None
            if t.label == "positive":
                block = block_tx_ids(con, t.block_id)
                coverage = round(len(evidence_ids & block) / len(block), 4)
            expected = PATTERN_NAMES.get(t.pattern_type or "", "none")
            rows.append(
                {
                    "alert_id": t.alert_id,
                    "label": t.label,
                    "late_block": t.runs_past_primary_period,
                    "expected_pattern": expected,
                    "predicted_pattern": case.get("pattern_hypothesis"),
                    "pattern_correct": case.get("pattern_hypothesis") == expected,
                    "recommended_action": case.get("recommended_action"),
                    "faithful": ver.get("faithful"),
                    "grounded": ver.get("grounded"),
                    "evidence_coverage": coverage,
                    "wall_ms": round(wall_ms, 1),
                    "error": error,
                    # Rejected or failed agent tool calls, for debugging tool-call validity.
                    "tool_errors": [
                        {"name": e["name"], "arguments": e["arguments"], "error": e["error"]}
                        for e in values.get("tool_log", [])
                        if e.get("by") == "agent" and not e.get("ok")
                    ],
                    **(case_metrics(values) if values else {}),
                }
            )
            print(
                f"  {t.alert_id} {t.label:8} {expected:>14} -> "
                f"{case.get('pattern_hypothesis')!s:<14} faithful={ver.get('faithful')}"
            )
    return rows


def aggregate(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r["error"]]
    pos = [r for r in ok if r["label"] == "positive"]
    neg = [r for r in ok if r["label"] == "benign"]

    def rate(items, key):
        vals = [r[key] for r in items if r[key] is not None]
        return round(sum(bool(v) for v in vals) / len(vals), 4) if vals else None

    def med(items, key):
        vals = [r[key] for r in items if r.get(key) is not None]
        return round(statistics.median(vals), 1) if vals else None

    def p95(items, key):
        vals = sorted(r[key] for r in items if r.get(key) is not None)
        return vals[min(len(vals) - 1, int(0.95 * len(vals)))] if vals else None

    return {
        "cases": len(rows),
        "errors": len(rows) - len(ok),
        "citation_faithfulness": rate(ok, "faithful"),
        "grounding": rate(ok, "grounded"),
        "schema_valid_rate": rate(ok, "schema_valid"),
        "pattern_accuracy": rate(ok, "pattern_correct"),
        "pattern_accuracy_positives": rate(pos, "pattern_correct"),
        "mean_evidence_coverage": round(statistics.mean(r["evidence_coverage"] for r in pos), 4)
        if pos
        else None,
        "false_escalations": sum(r["recommended_action"] == "escalate" for r in neg),
        "benign_cases": len(neg),
        "median_wall_ms": med(ok, "wall_ms"),
        "p95_wall_ms": p95(ok, "wall_ms"),
        "median_input_tokens": med(ok, "input_tokens"),
        "median_output_tokens": med(ok, "output_tokens"),
        "median_steps": med(ok, "steps"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", default="dev", choices=["dev", "eval"])
    parser.add_argument("--provider", default=os.environ.get("LLM_PROVIDER", "ollama"))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    if args.set == "eval" and not freeze_tag_exists():
        raise SystemExit(f"refusing the eval set: tag {FREEZE_TAG!r} does not exist yet")
    os.environ["LLM_PROVIDER"] = args.provider
    rows = asyncio.run(run_set(args.set, args.limit))
    headline = [r for r in rows if not r["late_block"]]
    late = [r for r in rows if r["late_block"]]
    provider = get_provider()
    summary = {
        "all": aggregate(rows),
        "headline_primary_period_only": aggregate(headline),
        "late_blocks_reported_separately": aggregate(late),
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evals" / "runs" / args.set
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{provider.provider}-{provider.model.replace(':', '_')}-{stamp}.json"
    record = {
        "created_utc": stamp,
        "alert_set": args.set,
        "provider": provider.provider,
        "model": provider.model,
        "prompt_version": PROMPT_VERSION,
        "note": "scripted: harness check only, not a model result"
        if provider.provider == "scripted"
        else "live run, uncached",
        "summary": summary,
        "cases": rows,
    }
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"written: {out}")


if __name__ == "__main__":
    main()
