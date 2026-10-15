"""The investigator copilot over the real MCP route on the synthetic tool DB (CI, no model)."""

from __future__ import annotations

import asyncio

import pytest

from aml_agent.agent import copilot
from aml_agent.audit import MemoryAudit
from aml_agent.llm.base import ChatResponse, ToolCall
from aml_agent.tools.client import connect_graph
from tests import synthetic

EM_DASH = chr(0x2014)
SEED = {"bank_id": 1, "account": "SEED0001"}
CASE = {
    "case_id": "case-copilot",
    "alert": {
        "alert_id": "syn-0001",
        "seed_bank": 1,
        "seed_account": "SEED0001",
        "window_start": "2022-09-02T00:00:00",
        "window_end": "2022-09-03T23:59:00",
    },
    "analysis": {
        "aliases": {"A0": [1, "SEED0001"], "A1": [2, "FAN00001"]},
        "case_file": "CASE FILE (synthetic)\nA0 = 1/SEED0001; seed",
        "triggers": [{"tx_id": 1}],
    },
    "draft": {
        "recommended_action": "escalate",
        "confidence": "low",
        "pattern_hypothesis": "fan-out",
        "summary": "A0 pays six accounts.",
        "limitations": "None.",
        "evidence": [{"tx_id": 2}],
    },
    "case_graph": {"edges": [{"src": "A0", "dst": "A1", "tx_ids": [1, 7]}]},
}


class FakeModel:
    """Replays a list of replies; a reply is either text or (tool name, arguments)."""

    provider = "fake"
    model = "fake-copilot"

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen_tools: list[list | None] = []

    async def chat(self, messages, tools=None):
        self.seen_tools.append(tools)
        if tools is None:
            return ChatResponse("From what I found, A0 paid six accounts.", [], 0, 100, 10)
        reply = self.replies.pop(0) if self.replies else self.replies_default()
        if isinstance(reply, tuple):
            name, args = reply
            return ChatResponse("", [ToolCall(f"c{len(self.seen_tools)}", name, args)], 0, 100, 10)
        return ChatResponse(reply, [], 0, 100, 10)

    def replies_default(self):
        return ("get_account_summary", SEED)


@pytest.fixture(scope="module")
def tool_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("copilotdb")
    synthetic.build(d)
    return d


def run(tool_dir, model, question="What did the subject pay out?"):
    async def main():
        audit = MemoryAudit()
        async with connect_graph(env={"PARQUET_DIR": str(tool_dir)}) as client:
            events = [e async for e in copilot.ask(model, client, CASE, question, [], audit)]
        return events, audit.events

    return asyncio.run(main())


def test_answer_uses_tools_and_checks_citations(tool_dir):
    model = FakeModel(
        [
            ("get_account_summary", SEED),
            ("get_transactions", {"tx_ids": [8]}),
            f"A0 sent six payments (tx 1, tx 8) {EM_DASH} and tx 424242 is made up.",
        ]
    )
    events, audit = run(tool_dir, model)
    tools = [e for e in events if e["type"] == "tool"]
    answer = events[-1]
    assert [t["text"] for t in tools] == [
        "Looked up account totals for the subject",
        "Read transactions",
    ]
    assert answer["type"] == "answer"
    assert answer["cited"] == [1, 8, 424242]
    # tx 1 is in the case, tx 8 came back from a tool; tx 424242 came from nowhere.
    assert answer["unverified"] == [424242]
    assert EM_DASH not in answer["answer"]
    types = [e["event_type"] for e in audit]
    assert types[0] == "copilot_question" and types[-1] == "copilot_answer"
    assert types.count("tool_call") == 2
    assert all(e["actor"] in ("analyst", "copilot") for e in audit)


def test_tool_calls_are_capped(tool_dir):
    model = FakeModel([])  # keeps asking for tools
    events, _ = run(tool_dir, model)
    answer = events[-1]
    assert len(answer["tools"]) == copilot.MAX_TOOL_CALLS
    assert answer["stopped"] == "lookup limit"
    # Once the cap is reached the model is offered no more tools, and still answers.
    assert model.seen_tools[-1] is None
    assert answer["answer"].startswith("From what I found")


def test_context_holds_the_case_and_assessment():
    text = copilot.context_message(CASE)
    assert '"seed_account": "SEED0001"' in text
    assert "CASE FILE (synthetic)" in text
    assert "recommendation escalate" in text and "tx 2" in text
    assert copilot.known_tx_ids(CASE) == {1, 2, 7}
