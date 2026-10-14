"""The code-built case file and account resolution (synthetic DB, runs in CI)."""

import asyncio
import time

import pytest

from aml_agent.agent.casefile import build_case_file, resolve_accounts
from aml_agent.tools.client import ToolResult
from aml_agent.tools.graph import GraphTools
from tests import synthetic
from tests.unit.test_agent_graph import ALERT


class LocalClient:
    """Calls the tools in process; the MCP route itself is covered by test_agent_graph."""

    def __init__(self, tools: GraphTools):
        self.tools = tools
        self.calls: list[str] = []

    async def call(self, name, arguments):
        self.calls.append(name)
        start = time.perf_counter()
        try:
            content = getattr(self.tools, name)(**arguments)
        except Exception as exc:
            return ToolResult(name, arguments, False, None, str(exc), 0.0)
        return ToolResult(name, arguments, True, content, None, time.perf_counter() - start)


@pytest.fixture(scope="module")
def case_file(tmp_path_factory):
    tools = GraphTools(synthetic.build(tmp_path_factory.mktemp("casefile")))
    client = LocalClient(tools)
    cf = asyncio.run(build_case_file(client, ALERT))
    yield cf, client
    tools.close()


def test_seed_is_a0_and_counterparties_are_labeled(case_file):
    cf, _ = case_file
    assert cf.aliases["A0"] == (1, "SEED0001")
    labeled = set(cf.aliases.values())
    assert {(2, "FAN00001"), (3, "HOP00001")} <= labeled
    assert "A0 = 1/SEED0001" in cf.text


def test_transfers_are_listed_sender_to_receiver(case_file):
    cf, _ = case_file
    label = {acc: alias for alias, acc in cf.aliases.items()}
    fan1, hop = label[(2, "FAN00001")], label[(3, "HOP00001")]
    assert f"{fan1} -> {hop}: 1 tx, 90 US Dollar" in cf.text
    assert f"A0 -> {fan1}: " in cf.text


def test_loop_through_the_seed_is_reported(case_file):
    # SEED0001 -> FAN00001 -> HOP00001 -> SEED0001 in time order.
    cf, _ = case_file
    label = {acc: alias for alias, acc in cf.aliases.items()}
    loops = [line for line in cf.text.splitlines() if " transfers: " in line]
    assert any(
        line.startswith("3 transfers: ")
        and f"A0 -> {label[(2, 'FAN00001')]}" in line
        and f"{label[(3, 'HOP00001')]} -> A0" in line
        for line in loops
    )


def test_rows_outside_the_alert_window_stay_out(case_file):
    cf, _ = case_file
    assert (3, "LATE0001") not in set(cf.aliases.values())
    assert synthetic.LATE_TX_ID not in cf.seen_tx_ids


def test_every_call_goes_through_the_client_and_is_logged(case_file):
    cf, client = case_file
    assert client.calls[0] == "get_account_summary"
    assert len(cf.tool_log) == len(client.calls)
    assert all(e["by"] == "system" for e in cf.tool_log)


def test_resolve_accounts():
    aliases = {"A0": (1, "SEED0001"), "A1": (2, "FAN00001")}
    known = {(1, "SEED0001"), (2, "FAN00001"), (3, "HOP00001")}
    accounts, problems = resolve_accounts(
        [
            "A0",
            "A1 (the hub)",
            "3/HOP00001",
            {"bank_id": 2, "account": "FAN00001"},
            "A9",
            "9/NOBODY01",
            "nonsense",
        ],
        aliases,
        known,
    )
    assert accounts == [(1, "SEED0001"), (2, "FAN00001"), (3, "HOP00001")]
    assert len(problems) == 3
    assert any("never returned by a tool" in p for p in problems)


def test_one_off_relationships_are_marked_and_candidates_listed(case_file):
    cf, _ = case_file
    label = {acc: alias for alias, acc in cf.aliases.items()}
    assert f"{label[(2, 'FAN00001')]} -> {label[(3, 'HOP00001')]}: 1 tx, 90 US Dollar" in cf.text
    assert "[one-off]" in cf.text
    assert "Pattern candidates found by code" in cf.text
    c1 = cf.candidates[0]
    assert c1["id"] == "C1" and c1["kind"] == "cycle"
    assert set(c1["accounts"]) == {"A0", label[(2, "FAN00001")], label[(3, "HOP00001")]}
    assert cf.graph["nodes"][0]["label"] == "A0" and cf.graph["edges"] and cf.graph["loops"]


def test_case_file_reports_risk_indicators(case_file):
    cf, client = case_file
    assert "get_account_behavior" in client.calls
    assert cf.risk["band"] in {"low", "medium", "high"}
    assert cf.risk["subject"]["rules"] == ["R2", "R3", "R4", "R5"]
    assert "Risk indicators (rules; score" in cf.text
