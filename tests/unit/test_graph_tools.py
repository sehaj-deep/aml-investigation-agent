"""Sprint 1 Verify: tools are read-only, bounded and validated (synthetic DB, runs in CI)."""

import duckdb
import pytest
from pydantic import ValidationError

from aml_agent.tools import graph
from aml_agent.tools.graph import GraphTools
from tests import synthetic

SEED = synthetic.SEED
WINDOW = {"window_start": "2022-09-01T00:00", "window_end": "2022-09-10T00:00"}


@pytest.fixture(scope="module")
def tools(tmp_path_factory):
    path = synthetic.build(tmp_path_factory.mktemp("tooldb"))
    t = GraphTools(path)
    yield t
    t.close()


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM transactions",
        "UPDATE transactions SET amount_paid = 0",
        "INSERT INTO banks VALUES (9, 'x', 'US')",
        "DROP TABLE banks",
        "CREATE TABLE x (a INT)",
    ],
)
def test_connection_rejects_writes(tools, sql):
    with pytest.raises(duckdb.Error):
        tools.con.execute(sql)


def test_no_write_tools_exist():
    names = {n for n in dir(GraphTools) if not n.startswith("_")}
    assert names == {
        "close",
        "get_account_summary",
        "get_neighbors",
        "trace_funds",
        "get_transfers_among",
        "get_account_behavior",
        "get_transactions",
    }


def test_hops_are_capped(tools):
    out = tools.trace_funds(**SEED, **WINDOW, hops=1000, max_edges=10**6)
    assert out["hops_applied"] == graph.MAX_HOPS
    assert out["capped"]["hops"] == {"requested": 1000, "applied": graph.MAX_HOPS}
    assert out["capped"]["max_edges"]["applied"] == graph.MAX_TRACE_EDGES


def test_neighbor_limit_is_capped(tools):
    out = tools.get_neighbors(**SEED, **WINDOW, limit=10**6)
    assert out["capped"]["limit"]["applied"] == graph.MAX_COUNTERPARTIES
    assert len(out["counterparties"]) == graph.MAX_COUNTERPARTIES
    assert out["total_counterparties"] > graph.MAX_COUNTERPARTIES
    assert out["truncated"] is True


def test_tx_ids_are_capped(tools):
    out = tools.get_transactions(tx_ids=list(range(1, 500)))
    assert out["capped"]["tx_ids"]["applied"] == graph.MAX_TX_IDS
    assert len(out["transactions"]) + len(out["not_found"]) == graph.MAX_TX_IDS


def test_long_window_is_capped(tools):
    out = tools.get_account_summary(
        **SEED, window_start="2022-09-01T00:00", window_end="2023-09-01T00:00"
    )
    assert out["window"]["end"] == "2022-09-10T23:59"  # clipped to the primary period


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bank_id": "abc", "account": "SEED0001"},
        {"bank_id": -1, "account": "SEED0001"},
        {"bank_id": 1, "account": "x'; DROP TABLE transactions; --"},
        {"bank_id": 1, "account": "SEED0001", "hops": 0},
        {"bank_id": 1, "account": "SEED0001", "hops": -3},
        {"bank_id": 1, "account": "SEED0001", "direction": "sideways"},
        {"bank_id": 1, "account": "SEED0001", "unexpected": True},
        {
            "bank_id": 1,
            "account": "SEED0001",
            "window_start": "2022-09-05T00:00",
            "window_end": "2022-09-01T00:00",
        },
    ],
)
def test_malformed_arguments_are_rejected(tools, kwargs):
    with pytest.raises(ValidationError):
        tools.trace_funds(**kwargs)


def test_malformed_tx_ids_are_rejected(tools):
    for bad in ([], [0], [-5], ["a"]):
        with pytest.raises(ValidationError):
            tools.get_transactions(tx_ids=bad)


def test_amounts_are_per_currency_and_self_transfers_hidden(tools):
    out = tools.get_account_summary(**SEED, **WINDOW)
    sent = {s["currency"]: s for s in out["sent"]}
    assert set(sent) == {"US Dollar", "Euro"}
    assert sent["US Dollar"]["total"] == "2100.000000"  # 100+200+...+600, self-transfers excluded
    assert sent["Euro"]["total"] == "50.000000"
    assert out["self_transfers_hidden"] == 2


def test_neighbors_include_self_transfers_only_on_request(tools):
    without = tools.get_neighbors(**SEED, **WINDOW, direction="out")
    assert all(c["account"] != "SEED0001" for c in without["counterparties"])
    with_self = tools.get_neighbors(**SEED, **WINDOW, direction="out", include_self_transfers=True)
    assert any(c["account"] == "SEED0001" for c in with_self["counterparties"])


def test_trace_respects_time_order(tools):
    out = tools.trace_funds(**SEED, **WINDOW, direction="forward", hops=3)
    hop2 = [e for e in out["edges"] if e["hop"] == 2]
    assert [e["to_account"] for e in hop2] == ["HOP00001"]
    # HOP00001 -> SEED0001 closes the cycle on hop 3; SEED0001 is not re-expanded.
    hop3 = [e for e in out["edges"] if e["hop"] == 3]
    assert [e["to_account"] for e in hop3] == ["SEED0001"]


def test_payment_format_hidden_by_default(tools, monkeypatch):
    out = tools.get_transactions(tx_ids=[1])
    assert "payment_format" not in out["transactions"][0]
    monkeypatch.setenv("TOOLS_SHOW_PAYMENT_FORMAT", "true")
    out = tools.get_transactions(tx_ids=[1])
    assert out["transactions"][0]["payment_format"] == "Wire"


def test_rows_after_primary_period_hidden_by_default(tools, monkeypatch):
    late_id = synthetic.LATE_TX_ID
    out = tools.get_account_summary(**SEED)
    assert "Swiss Franc" not in {s["currency"] for s in out["sent"]}
    assert tools.get_transactions(tx_ids=[late_id])["not_found"] == [late_id]
    neighbors = tools.get_neighbors(**SEED, direction="out")
    assert "LATE0001" not in {c["account"] for c in neighbors["counterparties"]}
    monkeypatch.setenv("TOOLS_SHOW_LATE_ROWS", "true")
    assert tools.get_transactions(tx_ids=[late_id])["transactions"][0]["tx_id"] == late_id
    out = tools.get_account_summary(**SEED)
    assert "Swiss Franc" in {s["currency"] for s in out["sent"]}


def test_neighbors_in_direction_only(tools):
    out = tools.get_neighbors(**SEED, **WINDOW, direction="in")
    assert out["direction"] == "in"
    assert {c["direction"] for c in out["counterparties"]} == {"in"}
    assert "HOP00001" in {c["account"] for c in out["counterparties"]}


@pytest.mark.parametrize(("given", "expected"), [("backward", "in"), ("forward", "out")])
def test_neighbor_direction_aliases(tools, given, expected):
    assert tools.get_neighbors(**SEED, **WINDOW, direction=given)["direction"] == expected


@pytest.mark.parametrize(("given", "expected"), [("in", "backward"), ("out", "forward")])
def test_trace_direction_aliases(tools, given, expected):
    assert tools.trace_funds(**SEED, **WINDOW, direction=given)["direction"] == expected


def test_neighbors_both_reports_requested_direction(tools):
    out = tools.get_neighbors(**SEED, **WINDOW, direction="both")
    assert out["direction"] == "both"
    assert {c["direction"] for c in out["counterparties"]} == {"in", "out"}


def test_neighbors_show_hub_hints(tools):
    # FAN00001's only sender is SEED0001, which is paid by 151 accounts (HOP00001 and
    # 150 BULK accounts) and pays 6 accounts (self-transfers excluded).
    out = tools.get_neighbors(bank_id=2, account="FAN00001", **WINDOW, direction="in")
    seed = out["counterparties"][0]
    assert (seed["account"], seed["their_senders"], seed["their_receivers"]) == ("SEED0001", 151, 6)


def test_transfers_among_returns_only_the_group_structure(tools):
    group = [
        {"bank_id": 1, "account": "SEED0001"},
        {"bank_id": 2, "account": "FAN00001"},
        {"bank_id": 3, "account": "HOP00001"},
        {"bank_id": 9, "account": "NOBODY01"},
    ]
    out = tools.get_transfers_among(accounts=group, **WINDOW)
    assert [t["tx_id"] for t in out["transfers"]] == [1, 7, 8, 11]  # the cycle, no self-transfers
    assert out["unconnected_accounts"] == [{"bank_id": 9, "account": "NOBODY01"}]
    euro = next(t for t in out["transfers"] if t["tx_id"] == 7)
    assert euro["currency_paid"] == "Euro"


def test_transfers_among_caps_and_validates(tools):
    many = [{"bank_id": 4, "account": f"BULK{i:04d}"} for i in range(40)]
    out = tools.get_transfers_among(accounts=[{"bank_id": 1, "account": "SEED0001"}, *many])
    assert out["capped"]["accounts"] == {"requested": 41, "applied": graph.MAX_GROUP_ACCOUNTS}
    with pytest.raises(ValidationError):
        tools.get_transfers_among(accounts=[{"bank_id": 1, "account": "SEED0001"}])
    with pytest.raises(ValidationError):
        tools.get_transfers_among(accounts=[{"bank_id": 1, "account": "bad one"}] * 2)
