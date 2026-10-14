"""Pattern candidates found by code in a case network (roadmap phase C).

Works on the case file's graph (accounts by label, transfers aggregated per pair and
direction, loops through the seed). It proposes ranked candidates; it does not decide
whether a case is suspicious. That stays with the detection score, the LLM analyst
and the human reviewer.

Signal: in the dev alerts, every pattern transfer sits on a ONE-OFF relationship (the
pair transacts once or twice in the window), while most ordinary activity repeats
(payroll-like pairs with 6 to 12 transfers). Keeping pairs with at most 2 transfers kept
100% of pattern transfers and removed 85% of the rest. Real-world analog: payments to
new or unusual counterparties that break an account's normal behavior. The effect is
especially clean in this simulator; say so when reporting.

Candidate kinds (names follow the dataset's AMLSim typologies):
- cycle: a loop through the seed (from the case file's 8-step traces);
- scatter-gather: an origin and a sink linked through two or more intermediaries;
- fan-in, fan-out, gather-scatter: a hub with several one-off senders and/or receivers;
- random: a time-ordered chain of one-off transfers through the seed.
Bipartite and stack patterns are often several disconnected pieces, so from one seed
they are rarely recoverable; the candidates do not try to name them.

Dev results (24 positives): the top candidate's kind is right in 13 (54%), the right
kind is among the top 3 in 17 (71%); excluding bipartite and stack, 72% and 94%.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

ONE_OFF_MAX_TRANSFERS = 2
MIN_HUB_LINKS = 3
MAX_CHAIN = 8
TOP_N = 3


@dataclass
class Candidate:
    kind: str
    score: float
    accounts: list[str]  # case-file labels
    tx_ids: list[int]
    reason: str
    id: str = ""
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "score": self.score,
            "accounts": self.accounts,
            "tx_ids": self.tx_ids,
            "reason": self.reason,
        }


def _tx(edges: list[dict]) -> list[int]:
    return [t for e in edges for t in e.get("tx_ids", [])]


def find_candidates(graph: dict, seed: str = "A0", top_n: int = TOP_N) -> list[Candidate]:
    one_off = [e for e in graph.get("edges", []) if e["n_tx"] <= ONE_OFF_MAX_TRANSFERS]
    out_e: dict[str, list[dict]] = defaultdict(list)
    in_e: dict[str, list[dict]] = defaultdict(list)
    adj: dict[str, set[str]] = defaultdict(set)
    for e in one_off:
        out_e[e["src"]].append(e)
        in_e[e["dst"]].append(e)
        adj[e["src"]].add(e["dst"])
        adj[e["dst"]].add(e["src"])

    # Accounts reachable from the seed over one-off relationships, with their distance.
    dist = {seed: 0}
    frontier = [seed]
    while frontier:
        nxt = []
        for x in frontier:
            for y in sorted(adj[x]):
                if y not in dist:
                    dist[y] = dist[x] + 1
                    nxt.append(y)
        frontier = nxt
    component = sorted(dist)

    found: list[Candidate] = []

    for loop in graph.get("loops") or []:
        nodes = sorted({x["src"] for x in loop} | {x["dst"] for x in loop})
        if len(nodes) >= 3:
            found.append(
                Candidate(
                    "cycle",
                    100 + len(nodes),
                    nodes,
                    [x["tx_id"] for x in loop],
                    f"money leaves the seed and returns to it through {len(nodes)} accounts",
                )
            )

    for origin in component:
        via_sink: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
        for first in out_e[origin]:
            for second in out_e[first["dst"]]:
                if second["dst"] != origin:
                    via_sink[second["dst"]].append((first, second))
        for sink, pairs in sorted(via_sink.items()):
            middle = sorted({p[0]["dst"] for p in pairs})
            if len(middle) >= 2:
                edges = [p[0] for p in pairs] + [p[1] for p in pairs]
                found.append(
                    Candidate(
                        "scatter-gather",
                        50 + len(middle),
                        sorted({origin, sink, *middle}),
                        _tx(edges),
                        f"{origin} pays {len(middle)} intermediaries that each pay {sink}",
                    )
                )

    for hub in component:
        n_in, n_out = len(in_e[hub]), len(out_e[hub])
        if n_in + n_out < MIN_HUB_LINKS:
            continue
        if n_in >= 2 and n_out >= 2:
            kind, edges = "gather-scatter", in_e[hub] + out_e[hub]
        elif n_in >= 2:
            kind, edges = "fan-in", in_e[hub]
        else:
            kind, edges = "fan-out", out_e[hub]
        members = sorted({hub} | {e["src"] for e in edges} | {e["dst"] for e in edges})
        found.append(
            Candidate(
                kind,
                20 + min(n_in + n_out, 30) - 5 * dist[hub],
                members,
                _tx(edges),
                f"{hub} has {n_in} one-off senders and {n_out} one-off receivers",
            )
        )

    def extend(path: list[dict], forward: bool) -> list[dict]:
        best = path
        tail = path[-1]["dst"] if forward else path[0]["src"]
        on_path = {p["src"] for p in path} | {p["dst"] for p in path}
        for e in out_e[tail] if forward else in_e[tail]:
            nxt = e["dst"] if forward else e["src"]
            if nxt in on_path or len(path) >= MAX_CHAIN:
                continue
            in_order = e["first"] >= path[-1]["first"] if forward else e["last"] <= path[0]["last"]
            if in_order:
                longer = extend([*path, e] if forward else [e, *path], forward)
                if len(longer) > len(best):
                    best = longer
        return best

    for start in sorted(out_e[seed] + in_e[seed], key=lambda e: (e["src"], e["dst"])):
        chain = extend(extend([start], True), False)
        if len(chain) >= 3:
            nodes = sorted({p["src"] for p in chain} | {p["dst"] for p in chain})
            found.append(
                Candidate(
                    "random",
                    10 + len(chain),
                    nodes,
                    _tx(chain),
                    f"a chain of {len(chain)} one-off transfers in time order",
                )
            )

    best: dict[tuple[str, tuple[str, ...]], Candidate] = {}
    for c in found:
        key = (c.kind, tuple(c.accounts))
        if key not in best or c.score > best[key].score:
            best[key] = c
    ranked = sorted(best.values(), key=lambda c: (-c.score, c.kind, c.accounts))[:top_n]
    for i, c in enumerate(ranked, start=1):
        c.id = f"C{i}"
    return ranked


def describe(candidates: list[Candidate]) -> str:
    """Case-file section listing the candidates for the model."""
    if not candidates:
        return "Pattern candidates found by code: none (no one-off structure around the seed)."
    lines = [
        "Pattern candidates found by code (from one-off relationships, pairs with at most "
        f"{ONE_OFF_MAX_TRANSFERS} transfers; ranked; a candidate is a lead, not a verdict):"
    ]
    for c in candidates:
        accounts = ", ".join(c.accounts)
        lines.append(
            f"{c.id}: {c.kind}; accounts {accounts}; {len(c.tx_ids)} transfers; {c.reason}"
        )
    return "\n".join(lines)
