"""Sprint 2 Verify (in-memory part): a case rebuilt from the audit log alone equals
the live run, the hash chain detects tampering, and every call is recorded.
Runs in CI on the synthetic DB with the scripted provider."""

import asyncio
import copy

import duckdb
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from aml_agent.agent.graph import compile_graph
from aml_agent.audit import MemoryAudit, reconstruct, timeline, verify_chain
from aml_agent.llm.scripted import ScriptedProvider
from aml_agent.tools.client import connect_graph
from aml_agent.verify.citations import CitationVerifier
from tests import synthetic
from tests.unit.test_agent_graph import ALERT

SPANS = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(SPANS))
trace.set_tracer_provider(_provider)


@pytest.fixture(scope="module")
def run_case(tmp_path_factory):
    d = tmp_path_factory.mktemp("auditdb")
    db = synthetic.build(d)
    audit = MemoryAudit()
    SPANS.clear()

    async def main():
        verifier = CitationVerifier(duckdb.connect(str(db), read_only=True))
        async with connect_graph(env={"PARQUET_DIR": str(d)}) as client:
            app = compile_graph(
                ScriptedProvider("basic"), client, InMemorySaver(), audit=audit, verifier=verifier
            )
            cfg = {"configurable": {"thread_id": "case-audit"}}
            await app.ainvoke({"case_id": "case-audit", "alert": ALERT}, cfg)
            more = {"action": "request_more", "reason": "Check inbound.", "reviewer": "r1"}
            await app.ainvoke(Command(resume=more), cfg)
            approve = {"action": "approve", "reason": "Supported.", "reviewer": "r1"}
            await app.ainvoke(Command(resume=approve), cfg)
            return (await app.aget_state(cfg)).values

    values = asyncio.run(main())
    return values, audit.for_case("case-audit")


def test_case_rebuilt_from_log_equals_live_run(run_case):
    values, events = run_case
    rebuilt = reconstruct(events)
    assert rebuilt == values
    assert rebuilt["status"] == "approved"


def test_hash_chain_is_valid_and_detects_tampering(run_case):
    _, events = run_case
    assert verify_chain(events)
    tampered = copy.deepcopy(events)
    tampered[5]["payload"]["node"] = "something-else"
    assert not verify_chain(tampered)
    dropped = [e for i, e in enumerate(events) if i != 3]
    assert not verify_chain(dropped)


def test_every_model_and_tool_call_is_recorded(run_case):
    values, events = run_case
    model_calls = [e for e in events if e["event_type"] == "model_call"]
    assert len(model_calls) == values["steps"] + values["schema_attempts"]
    for e in model_calls:
        p = e["payload"]
        assert p["provider"] == "scripted" and p["model"] == "scripted-basic"
        assert p["prompt_version"] == values["prompt_version"]
        assert p["input_tokens"] > 0
    tool_calls = [e for e in events if e["event_type"] == "tool_call"]
    assert len(tool_calls) == len([t for t in values["tool_log"] if t.get("executed", True)])
    assert all("result" in e["payload"] and "duration_ms" in e["payload"] for e in tool_calls)


def test_decisions_and_interrupts_are_recorded(run_case):
    _, events = run_case
    types = [e["event_type"] for e in events]
    assert types.count("node_interrupted") == 2
    finished = [e["payload"]["node"] for e in events if e["event_type"] == "node_finished"]
    assert finished[-1] == "finalize"
    assert finished.count("human_review") == 2


def test_verification_ran_and_passed(run_case):
    values, _ = run_case
    assert values["verification"]["faithful"] is True
    assert values["verification"]["grounded"] is True
    assert not any(w.startswith("VERIFICATION_FAILED") for w in values["warnings"])


def test_timeline_is_readable(run_case):
    _, events = run_case
    lines = timeline(events)
    assert len(lines) == len(events)
    assert any("model_call" in line and "scripted/scripted-basic" in line for line in lines)


def test_spans_cover_nodes_models_and_tools(run_case):
    names = {s.name for s in SPANS.get_finished_spans()}
    assert {"node.triage", "node.agent", "node.verify", "model.chat"} <= names
    assert "tool.get_neighbors" in names
