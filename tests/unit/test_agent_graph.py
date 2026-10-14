"""Sprint 1 Verify: workflow behavior with a scripted model over the real MCP route.

The MCP server runs as a subprocess on the synthetic tool DB; the agent reaches
data only through it. Runs in CI (no dataset, no live model).
"""

import asyncio
import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import ValidationError

from aml_agent.agent.graph import Budget, FinalizeRefused, compile_graph
from aml_agent.llm.scripted import ScriptedProvider
from aml_agent.metrics import case_metrics
from aml_agent.tools.client import connect_graph
from tests import synthetic

EM_DASH = chr(0x2014)
ALERT = {
    "alert_id": "syn-0001",
    "seed_bank": 1,
    "seed_account": "SEED0001",
    "window_start": "2022-09-01T00:00:00",
    "window_end": "2022-09-10T00:00:00",
}
APPROVE = {"action": "approve", "reason": "Evidence supports it.", "reviewer": "tester"}


@pytest.fixture(scope="module")
def tool_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("agentdb")
    synthetic.build(d)
    return d


def run(tool_dir, policy, steps, budget=None):
    """Run `steps(app, cfg)` against a fresh graph; returns its result."""

    async def main():
        async with connect_graph(env={"PARQUET_DIR": str(tool_dir)}) as client:
            app = compile_graph(ScriptedProvider(policy), client, InMemorySaver(), budget)
            cfg = {"configurable": {"thread_id": "t1"}}
            return await steps(app, cfg)

    return asyncio.run(main())


async def start(app, cfg):
    await app.ainvoke({"case_id": "case-syn", "alert": ALERT}, cfg)
    return await app.aget_state(cfg)


def test_case_waits_for_approval_then_finalizes(tool_dir):
    async def steps(app, cfg):
        paused = await start(app, cfg)
        out = await app.ainvoke(Command(resume=APPROVE), cfg)
        return paused, out

    paused, out = run(tool_dir, "basic", steps)
    assert paused.next == ("human_review",)
    assert paused.values["status"] == "pending_review"
    case = paused.values["case"]
    assert case["pattern_hypothesis"] == "fan-out"
    assert case["evidence"], "evidence rows are filled from the data"
    assert all(e["tx_id"] in paused.values["seen_tx_ids"] for e in case["evidence"])
    assert out["status"] == "approved"
    m = case_metrics(paused.values)
    assert m["tool_call_validity"] == 1.0 and m["schema_valid"]


def test_agent_tool_calls_go_through_mcp_only(tool_dir):
    paused = run(tool_dir, "basic", start)
    names = [e["name"] for e in paused.values["tool_log"]]
    assert names[0] == "get_account_summary"
    assert set(names) <= {"get_account_summary", "get_neighbors", "trace_funds", "get_transactions"}


def test_finalize_without_decision_is_refused(tool_dir):
    async def steps(app, cfg):
        await start(app, cfg)
        with pytest.raises(FinalizeRefused):
            await app.ainvoke(Command(goto="finalize"), cfg)
        return await app.aget_state(cfg)

    state = run(tool_dir, "basic", steps)
    assert state.values["status"] == "pending_review"


def test_malformed_decision_is_rejected(tool_dir):
    async def steps(app, cfg):
        await start(app, cfg)
        with pytest.raises(ValidationError):
            await app.ainvoke(Command(resume={"action": "approve"}), cfg)
        with pytest.raises(ValidationError):
            await app.ainvoke(Command(resume={**APPROVE, "action": "finalize"}), cfg)
        return await app.aget_state(cfg)

    state = run(tool_dir, "basic", steps)
    assert state.next == ("human_review",)


def test_looping_alert_stops_at_step_cap(tool_dir):
    paused = run(tool_dir, "loop", start, Budget(max_steps=5))
    assert paused.values["round_steps"] == 5
    assert paused.values["budget_exhausted"] == "step limit 5"
    assert paused.next == ("human_review",)


def test_tool_call_cap(tool_dir):
    paused = run(tool_dir, "loop", start, Budget(max_steps=50, max_tool_calls=3))
    assert paused.values["round_tool_calls"] == 3
    assert paused.values["budget_exhausted"] == "tool call limit 3"


def test_token_cap(tool_dir):
    paused = run(tool_dir, "loop", start, Budget(max_steps=50, max_tokens=5000))
    assert paused.values["budget_exhausted"] == "token limit 5000"


def test_invalid_tool_calls_are_counted_and_survived(tool_dir):
    paused = run(tool_dir, "bad_tool", start)
    m = case_metrics(paused.values)
    assert m["tool_calls"] == 4
    assert m["valid_tool_calls"] == 2
    assert m["tool_call_validity"] == 0.5
    assert paused.values["status"] == "pending_review"


def test_schema_failure_is_retried(tool_dir):
    paused = run(tool_dir, "bad_json", start)
    assert paused.values["schema_failures"] == 1
    assert paused.values["hypothesis"]["pattern_hypothesis"] == "fan-out"


def test_em_dash_is_removed_from_narrative(tool_dir):
    paused = run(tool_dir, "emdash", start)
    assert EM_DASH not in json.dumps(paused.values["case"], ensure_ascii=False)
    assert "em dash removed from summary" in paused.values["warnings"]


def test_benign_conclusion(tool_dir):
    paused = run(tool_dir, "none", start)
    case = paused.values["case"]
    assert case["pattern_hypothesis"] == "none"
    assert case["recommended_action"] == "close"
    assert case["evidence"] == []


def test_request_more_reinvestigates_then_round_limit(tool_dir):
    more = {"action": "request_more", "reason": "Look at inbound flows.", "reviewer": "tester"}

    async def steps(app, cfg):
        await start(app, cfg)
        await app.ainvoke(Command(resume=more), cfg)
        first = await app.aget_state(cfg)
        await app.ainvoke(Command(resume=more), cfg)
        await app.ainvoke(Command(resume=more), cfg)
        third = await app.aget_state(cfg)
        out = await app.ainvoke(Command(resume=APPROVE), cfg)
        return first, third, out

    first, third, out = run(tool_dir, "basic", steps, Budget(max_review_rounds=2))
    assert first.values["review_round"] == 1 and first.next == ("human_review",)
    assert third.values["review_round"] == 2
    assert any("review-round limit" in w for w in third.values["warnings"])
    assert out["status"] == "approved"
