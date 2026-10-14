"""Sprint 1 model bake-off on DEV alerts only (PRD section 9, rule 3).

Runs each model on the same seeded sample of dev alerts (half positive, half
benign) up to the human-approval pause, and reports per model: tool-call
validity, schema-valid output rate, steps, tokens and latency. Pattern accuracy
and false escalations are shown as diagnostics only (dev set, small n).

    python scripts/bakeoff.py --models gpt-oss:20b-cloud,gemma4:31b-cloud --n 20
    python scripts/bakeoff.py --provider scripted --n 4      (harness check, not results)

The evaluation set is refused: it must never be used for model or prompt choice.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from aml_agent.agent.graph import compile_graph
from aml_agent.agent.prompts import PROMPT_VERSION
from aml_agent.alerts.io import read_alerts, read_truth
from aml_agent.llm.base import get_provider
from aml_agent.metrics import case_metrics
from aml_agent.tools.client import connect_graph

OUT_DIR = Path(__file__).resolve().parents[1] / "evals" / "runs" / "bakeoff"
TRUTH_NAMES = {
    "FAN-OUT": "fan-out",
    "FAN-IN": "fan-in",
    "CYCLE": "cycle",
    "GATHER-SCATTER": "gather-scatter",
    "SCATTER-GATHER": "scatter-gather",
    "BIPARTITE": "bipartite",
    "STACK": "stack",
    "RANDOM": "random",
}


def sample_dev(n: int, seed: int) -> list[tuple]:
    alerts = {a.alert_id: a for a in read_alerts("dev")}
    truth = read_truth("dev")
    pos = sorted(t.alert_id for t in truth if t.label == "positive")
    neg = sorted(t.alert_id for t in truth if t.label == "benign")
    rng = random.Random(seed)
    picked = rng.sample(pos, n // 2) + rng.sample(neg, n - n // 2)
    by_id = {t.alert_id: t for t in truth}
    return [(alerts[i], by_id[i]) for i in sorted(picked)]


async def run_model(sample: list[tuple]) -> dict:
    provider = get_provider()
    rows = []
    async with connect_graph() as client:
        app = compile_graph(provider, client, InMemorySaver())
        for alert, truth in sample:
            cfg = {"configurable": {"thread_id": alert.alert_id}}
            start = time.perf_counter()
            error = None
            try:
                await app.ainvoke(
                    {"case_id": alert.alert_id, "alert": alert.model_dump(mode="json")}, cfg
                )
            except Exception as exc:  # record and continue; a failure is a result
                error = f"{type(exc).__name__}: {exc}"
            wall = (time.perf_counter() - start) * 1000
            values = (await app.aget_state(cfg)).values
            m = case_metrics(values) if values else {}
            case = values.get("case") or {}
            expected = TRUTH_NAMES.get(truth.pattern_type, "none")
            rows.append(
                {
                    "alert_id": alert.alert_id,
                    "label": truth.label,
                    "expected_pattern": expected,
                    "predicted_pattern": case.get("pattern_hypothesis"),
                    "recommended_action": case.get("recommended_action"),
                    "wall_ms": round(wall, 1),
                    "error": error,
                    **m,
                }
            )
            print(f"  {alert.alert_id} {truth.label:8} -> {case.get('pattern_hypothesis')}")
    return {"provider": provider.provider, "model": provider.model, "cases": rows}


def summarize(run: dict) -> dict:
    cases = run["cases"]
    ok = [c for c in cases if not c["error"]]
    calls = sum(c.get("tool_calls", 0) + c.get("provider_invalid_tool_calls", 0) for c in ok)
    valid = sum(c.get("valid_tool_calls", 0) for c in ok)

    def med(key):
        vals = [c[key] for c in ok if c.get(key) is not None]
        return round(statistics.median(vals), 1) if vals else None

    benign = [c for c in ok if c["label"] == "benign"]
    return {
        "model": run["model"],
        "cases": len(cases),
        "errors": len(cases) - len(ok),
        "tool_call_validity": round(valid / calls, 4) if calls else None,
        "schema_valid_rate": round(sum(c["schema_valid"] for c in ok) / len(ok), 4) if ok else None,
        "median_steps": med("steps"),
        "median_input_tokens": med("input_tokens"),
        "median_output_tokens": med("output_tokens"),
        "median_wall_ms": med("wall_ms"),
        "diagnostic_pattern_accuracy": round(
            sum(c["predicted_pattern"] == c["expected_pattern"] for c in ok) / len(ok), 4
        )
        if ok
        else None,
        "diagnostic_false_escalations": sum(c["recommended_action"] == "escalate" for c in benign),
        "benign_cases": len(benign),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default=os.environ.get("LLM_MODEL", "gpt-oss:20b-cloud"))
    parser.add_argument("--provider", default=os.environ.get("LLM_PROVIDER", "ollama"))
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--alert-set", default="dev")
    args = parser.parse_args()
    if args.alert_set != "dev":
        raise SystemExit("the bake-off runs on dev alerts only; the eval set is never for tuning")

    sample = sample_dev(args.n, args.seed)
    os.environ["LLM_PROVIDER"] = args.provider
    runs = []
    for model in args.models.split(","):
        os.environ["LLM_MODEL"] = model.strip()
        print(f"== {args.provider} {model}")
        runs.append(asyncio.run(run_model(sample)))
    summary = [summarize(r) for r in runs]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"bakeoff-{args.provider}-{stamp}.json"
    record = {
        "created_utc": stamp,
        "prompt_version": PROMPT_VERSION,
        "provider": args.provider,
        "alert_set": "dev",
        "sample_seed": args.seed,
        "alert_ids": [a.alert_id for a, _ in sample],
        "note": "scripted runs test the harness only; they are not model results"
        if args.provider == "scripted"
        else "live run; uncached",
        "summary": summary,
        "runs": runs,
    }
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"written: {out}")


if __name__ == "__main__":
    main()
