"""Per-case metrics derived from the workflow state (section 11, Sprint 1 rows)."""

from __future__ import annotations

import statistics


def case_metrics(values: dict) -> dict:
    agent_calls = [e for e in values.get("tool_log", []) if e.get("by") == "agent"]
    attempted = [e for e in agent_calls if e.get("error") != "budget"]
    valid = [e for e in attempted if e.get("ok")]
    durations = [e["duration_ms"] for e in values.get("tool_log", []) if e.get("executed", True)]
    attempts = values.get("schema_attempts", 0)
    # invalid_tool_calls counts unparseable calls (provider), unknown tools and calls the
    # server rejected; the provider share is what the tool log cannot see.
    provider_invalid = values.get("invalid_tool_calls", 0) - (len(attempted) - len(valid))
    denominator = len(attempted) + provider_invalid
    return {
        "steps": values.get("steps", 0),
        "tool_calls": len(attempted),
        "valid_tool_calls": len(valid),
        "tool_call_validity": round(len(valid) / denominator, 4) if denominator else None,
        "provider_invalid_tool_calls": provider_invalid,
        "schema_attempts": attempts,
        "schema_failures": values.get("schema_failures", 0),
        "schema_valid": values.get("case") is not None
        and not any("MODEL_OUTPUT_INVALID" in w for w in values.get("warnings", [])),
        "input_tokens": values.get("input_tokens", 0),
        "output_tokens": values.get("output_tokens", 0),
        "llm_latency_ms": round(values.get("llm_latency_ms", 0.0), 1),
        "tool_latency_median_ms": round(statistics.median(durations), 1) if durations else None,
        "tool_latency_max_ms": round(max(durations), 1) if durations else None,
        "budget_exhausted": values.get("budget_exhausted"),
        "review_rounds": values.get("review_round", 0),
    }
