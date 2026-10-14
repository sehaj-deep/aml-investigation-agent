"""Pattern candidates on small hand-built case networks with known answers."""

from aml_agent.analysis.patterns import describe, find_candidates

T = "2022-09-0{}T10:00"


def edge(src, dst, n_tx=1, day=2, tx=None):
    ts = T.format(day)
    return {
        "src": src,
        "dst": dst,
        "n_tx": n_tx,
        "first": ts,
        "last": ts,
        "tx_ids": [tx if tx is not None else hash((src, dst)) % 100000],
        "totals": [],
    }


def kinds(graph):
    return [(c.kind, c.accounts) for c in find_candidates(graph)]


def test_fan_in_ignores_repeated_relationships():
    g = {"edges": [edge("A1", "A0"), edge("A2", "A0"), edge("A3", "A0"), edge("A9", "A0", n_tx=10)]}
    c1 = find_candidates(g)[0]
    assert (c1.id, c1.kind, c1.accounts) == ("C1", "fan-in", ["A0", "A1", "A2", "A3"])


def test_fan_out():
    g = {"edges": [edge("A0", "A1"), edge("A0", "A2"), edge("A0", "A3")]}
    assert kinds(g)[0] == ("fan-out", ["A0", "A1", "A2", "A3"])


def test_gather_scatter_through_a_hub_one_step_away():
    g = {
        "edges": [
            edge("A0", "A5", day=2),
            edge("A1", "A5", day=2),
            edge("A5", "A6", day=3),
            edge("A5", "A7", day=3),
        ]
    }
    assert kinds(g)[0] == ("gather-scatter", ["A0", "A1", "A5", "A6", "A7"])


def test_scatter_gather_origin_to_sink():
    g = {
        "edges": [
            edge("A0", "A1", day=2),
            edge("A0", "A2", day=2),
            edge("A1", "A5", day=3),
            edge("A2", "A5", day=3),
        ]
    }
    assert kinds(g)[0] == ("scatter-gather", ["A0", "A1", "A2", "A5"])


def test_cycle_from_case_file_loop_ranks_first():
    loop = [
        {"tx_id": 1, "src": "A0", "dst": "A1", "ts": T.format(2)},
        {"tx_id": 2, "src": "A1", "dst": "A2", "ts": T.format(3)},
        {"tx_id": 3, "src": "A2", "dst": "A0", "ts": T.format(4)},
    ]
    g = {"edges": [edge("A0", "A1"), edge("A0", "A3"), edge("A0", "A4")], "loops": [loop]}
    c1 = find_candidates(g)[0]
    assert (c1.kind, c1.accounts, c1.tx_ids) == ("cycle", ["A0", "A1", "A2"], [1, 2, 3])


def test_time_ordered_chain_is_random():
    g = {
        "edges": [
            edge("A0", "A1", day=2),
            edge("A1", "A2", day=3),
            edge("A2", "A3", day=4),
            edge("A3", "A4", day=1),  # earlier: breaks time order, not part of the chain
        ]
    }
    assert ("random", ["A0", "A1", "A2", "A3"]) in kinds(g)


def test_only_repeated_activity_gives_no_candidates():
    g = {"edges": [edge("A0", "A1", n_tx=8), edge("A2", "A0", n_tx=12)]}
    assert find_candidates(g) == []
    assert "none" in describe([])


def test_describe_lists_ids_and_accounts():
    g = {"edges": [edge("A1", "A0"), edge("A2", "A0"), edge("A3", "A0")]}
    text = describe(find_candidates(g))
    assert "C1: fan-in; accounts A0, A1, A2, A3; 3 transfers" in text
