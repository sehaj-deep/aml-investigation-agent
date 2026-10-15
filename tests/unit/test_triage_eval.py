"""Scoring of the final AI-analyst evaluation (evals/run_triage_eval.py)."""

from __future__ import annotations

from evals import run_triage_eval as ev


def row(label, action, priority="high", **kw):
    base = {
        "alert_id": f"A{id(kw)}",
        "priority": priority,
        "label": label,
        "action": action,
        "faithful": True,
        "draft_invalid": False,
        "guidance_kept": 1,
        "guidance_rejected": 0,
        "seconds": 10.0,
        "error": None,
        "input_tokens": 900,
        "output_tokens": 100,
        "tool_calls": 2,
    }
    return {**base, **kw}


def test_triage_shares_split_laundering_and_false_alarms():
    rows = [
        row("positive", "escalate"),
        row("positive", "close"),
        row("benign", "close", priority="low"),
        row("benign", "needs_more_info", priority="low", guidance_kept=0, guidance_rejected=1),
    ]
    s = ev.summarize(rows)
    assert s["triage"]["laundering"] == {
        "n": 2,
        "escalate": 0.5,
        "needs_more_info": 0.0,
        "close": 0.5,
    }
    assert s["triage"]["false_alarms"]["close"] == 0.5
    assert s["by_priority"]["low"]["laundering"]["n"] == 0
    assert s["faithfulness"]["guidance_quote_precision"] == 0.75
    assert s["cost"]["tokens_total"] == 4000


def test_failed_cases_are_counted_not_scored():
    s = ev.summarize([row("positive", None, error="RuntimeError: x"), row("benign", "close")])
    assert s["errors"] == 1 and s["triage"]["alerts"] == 1
