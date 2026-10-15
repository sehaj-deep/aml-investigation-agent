"""The case file: what every investigation starts with, assembled by code.

Live runs showed the model exploring too little or in the wrong direction, so the
exploration that code can do reliably is done by code (FR-3), through the same
MCP tools and audit trail as the model's own calls:

- the seed's account summary;
- the seed's counterparties in both directions (step 1);
- the counterparties of every step-1 account that is not a busy hub (step 2);
- money traces of up to 8 steps forward and backward from the seed, reporting loops:
  an account that money from the seed later reaches AND that earlier sent money
  which reached the seed (a cycle through the seed, wherever the seed sits in it).

On the dev alerts, the step-1 and step-2 view holds 75% of each pattern's
transactions on average (84% are connected to the seed at all), and the 8-step
trace covers the chain patterns (cycle, random). Accounts get short labels (A0 is
the seed) so the model can name them without copying IDs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from aml_agent.analysis import risk as risk_rules
from aml_agent.analysis.patterns import (
    ONE_OFF_MAX_TRANSFERS,
    describe,
    find_candidates,
)
from aml_agent.tools.client import GraphClient

SEED_NEIGHBOR_LIMIT = 100
STEP2_NEIGHBOR_LIMIT = 50
EXPAND_MAX_DEGREE = 40  # step-1 accounts with more counterparties are busy hubs
MAX_EXPANSIONS = 25
ROUND_TRIP_HOPS = 8
MAX_ROUND_TRIPS = 5
MAX_TRANSFER_LINES = 300

ALIAS_RE = re.compile(r"^A(\d+)$")
DIRECT_RE = re.compile(r"^(\d+)\s*/\s*([0-9A-Z]{1,20})$")

Account = tuple[int, str]


@dataclass
class CaseFile:
    text: str
    aliases: dict[str, Account]
    seen_tx_ids: list[int]
    seen_accounts: list[Account]
    tool_log: list[dict] = field(default_factory=list)
    # Structured network for analytics and the UI: nodes, edges (aggregated per pair and
    # direction, with up to 20 tx_ids each) and loops through the seed.
    graph: dict = field(default_factory=dict)
    # Ranked pattern candidates found by code (aml_agent/analysis/patterns.py).
    candidates: list[dict] = field(default_factory=list)
    # Rules-based risk score and reasons (aml_agent/analysis/risk.py).
    risk: dict = field(default_factory=dict)
    # The payments transaction monitoring flagged, with account labels (for the UI).
    triggers: list[dict] = field(default_factory=list)


def _short(amount: str) -> str:
    """Exact amount without trailing zeros: "2964.490000" -> "2964.49"."""
    return format(Decimal(amount).normalize(), "f")


def _totals(totals: list[dict]) -> str:
    return ", ".join(f"{_short(t['total'])} {t['currency']}" for t in totals)


class _Builder:
    def __init__(self, seed: Account):
        self.aliases: dict[Account, str] = {}
        self.info: dict[Account, dict] = {}
        self.edges: dict[tuple[Account, Account], dict] = {}
        self.tx_ids: list[int] = []
        self.label(seed, hop=0)

    def label(self, acc: Account, hop: int | str, **info: Any) -> str:
        if acc not in self.aliases:
            self.aliases[acc] = f"A{len(self.aliases)}"
            self.info[acc] = {"hop": hop}
        self.info[acc].update({k: v for k, v in info.items() if v is not None})
        return self.aliases[acc]

    def add_counterparties(self, here: Account, result: dict, hop: int) -> None:
        for c in result["counterparties"]:
            other = (c["bank_id"], c["account"])
            self.label(
                other,
                hop=hop,
                senders=c.get("their_senders"),
                receivers=c.get("their_receivers"),
                jurisdiction=c.get("jurisdiction"),
            )
            key = (here, other) if c["direction"] == "out" else (other, here)
            if key not in self.edges:
                self.edges[key] = {
                    "n_tx": c["n_tx"],
                    "totals": c["totals"],
                    "first": c["first_ts"],
                    "last": c["last_ts"],
                    "tx_ids": c["tx_ids"],
                }
            self.tx_ids.extend(c["tx_ids"])


def _src(e: dict) -> Account:
    return (e["from_bank"], e["from_account"])


def _dst(e: dict) -> Account:
    return (e["to_bank"], e["to_account"])


def _path(index: dict[Account, dict], start: Account, seed: Account, step) -> list[dict] | None:
    """Walk lowest-hop edges from `start` back to the seed (step picks the next account)."""
    path: list[dict] = []
    cur = start
    while cur != seed:
        e = index.get(cur)
        if e is None or len(path) > ROUND_TRIP_HOPS:
            return None
        path.append(e)
        cur = step(e)
    return path


def _loops(forward: dict | None, backward: dict | None, seed: Account) -> list[list[dict]]:
    """Loops through the seed: money leaving the seed reaches an account M (forward
    trace), and money from M earlier reached the seed (backward trace)."""
    if not forward or not backward:
        return []
    reached_fwd: dict[Account, dict] = {}  # account -> lowest-hop edge arriving at it
    for e in forward["edges"]:
        if _dst(e) not in reached_fwd or e["hop"] < reached_fwd[_dst(e)]["hop"]:
            reached_fwd[_dst(e)] = e
    reached_bwd: dict[Account, dict] = {}  # account -> lowest-hop edge leaving it
    for e in backward["edges"]:
        if _src(e) not in reached_bwd or e["hop"] < reached_bwd[_src(e)]["hop"]:
            reached_bwd[_src(e)] = e
    loops = []
    if seed in reached_fwd:  # money that left the seed came straight back to it
        last = reached_fwd[seed]
        out = _path(reached_fwd, _src(last), seed, _src)
        if out is not None:
            loops.append([*reversed(out), last])
    for meet in sorted((set(reached_fwd) & set(reached_bwd)) - {seed}):
        out = _path(reached_fwd, meet, seed, _src)
        back = _path(reached_bwd, meet, seed, _dst)
        if out is not None and back is not None:
            loops.append([*reversed(out), *back])
    loops.sort(key=len)
    return loops[:MAX_ROUND_TRIPS]


async def build_case_file(client: GraphClient, alert: dict) -> CaseFile:
    seed: Account = (alert["seed_bank"], alert["seed_account"])
    window = {"window_start": alert["window_start"], "window_end": alert["window_end"]}
    base = {"bank_id": seed[0], "account": seed[1], **window}
    log: list[dict] = []

    async def call(name: str, args: dict) -> dict | None:
        result = await client.call(name, args)
        log.append(
            {
                "by": "system",
                "step": 0,
                "name": name,
                "arguments": args,
                "ok": result.ok,
                "error": result.error,
                "duration_ms": round(result.duration_ms, 1),
                "executed": True,
            }
        )
        return result.content if result.ok else None

    b = _Builder(seed)
    summary = await call("get_account_summary", base)
    if summary:
        b.label(
            seed,
            hop=0,
            senders=summary["counterparties_in"],
            receivers=summary["counterparties_out"],
            jurisdiction=summary["account"].get("jurisdiction"),
        )

    # The payments transaction monitoring flagged come first: they are why the case exists.
    triggers: list[dict] = []
    if alert.get("trigger_tx_ids"):
        got = await call("get_transactions", {"tx_ids": list(alert["trigger_tx_ids"])})
        for t in (got or {}).get("transactions", []):
            for acc in ((t["from_bank"], t["from_account"]), (t["to_bank"], t["to_account"])):
                b.label(acc, hop=1)
            b.tx_ids.append(t["tx_id"])
            triggers.append(t)

    step1 = await call("get_neighbors", {**base, "direction": "both", "limit": SEED_NEIGHBOR_LIMIT})
    not_expanded: list[Account] = []
    if step1:
        b.add_counterparties(seed, step1, hop=1)
        expansions = 0
        seen_step1: set[Account] = set()
        for c in step1["counterparties"]:
            acc = (c["bank_id"], c["account"])
            if acc in seen_step1:
                continue
            seen_step1.add(acc)
            degree = c.get("their_senders", 0) + c.get("their_receivers", 0)
            if degree > EXPAND_MAX_DEGREE or expansions >= MAX_EXPANSIONS:
                not_expanded.append(acc)
                continue
            expansions += 1
            step2 = await call(
                "get_neighbors",
                {
                    "bank_id": acc[0],
                    "account": acc[1],
                    **window,
                    "direction": "both",
                    "limit": STEP2_NEIGHBOR_LIMIT,
                },
            )
            if step2:
                b.add_counterparties(acc, step2, hop=2)

    traces = {
        direction: await call(
            "trace_funds",
            {**base, "direction": direction, "hops": ROUND_TRIP_HOPS, "max_edges": 300},
        )
        for direction in ("forward", "backward")
    }
    trips = _loops(traces["forward"], traces["backward"], seed)
    for path in trips:
        for e in path:
            for acc in ((e["from_bank"], e["from_account"]), (e["to_bank"], e["to_account"])):
                b.label(acc, hop="trace")
            b.tx_ids.append(e["tx_id"])

    # Text for the model.
    lines = [
        "CASE FILE (assembled by code from the tools; labels A0, A1, ... name accounts, "
        "A0 is the seed).",
        f"Window: {alert['window_start']} to {alert['window_end']}.",
    ]
    if summary:
        sent = "; ".join(
            f"{s['n_tx']} tx, {_short(s['total'])} {s['currency']}" for s in summary["sent"]
        )
        received = "; ".join(
            f"{s['n_tx']} tx, {_short(s['total'])} {s['currency']}" for s in summary["received"]
        )
        lines.append(f"Seed sent: {sent or 'nothing'}. Seed received: {received or 'nothing'}.")
    if alert.get("detection_score") is not None:
        lines.append("")
        lines.append(
            "WHY THIS ALERT WAS RAISED (transaction monitoring model; statistical reasons, "
            "not proof; most alerts are false alarms):"
        )
        priority = alert.get("priority")
        if priority == "sample":
            priority = "sample (below-the-line: scored just under the alert threshold)"
        lines.append(
            f"Priority {priority}, score {alert['detection_score']:.3f} "
            f"(rank {alert.get('detection_rank')} in the queue)."
        )
        reasons = "; ".join(
            f["label"] + ("" if f.get("value") is None else f" ({f['value']:g})")
            for f in alert.get("detection_factors") or []
        )
        lines.append(f"Main reasons for the strongest flagged payment: {reasons or 'not given'}.")
        lines.append(f"Flagged payments ({len(triggers)}):")
        for t in triggers:
            src = b.aliases[(t["from_bank"], t["from_account"])]
            dst = b.aliases[(t["to_bank"], t["to_account"])]
            line = (
                f"tx {t['tx_id']} {t['timestamp']} {src} -> {dst}: "
                f"paid {_short(t['amount_paid'])} {t['currency_paid']}"
            )
            if t["currency_received"] != t["currency_paid"]:
                line += f", received {_short(t['amount_received'])} {t['currency_received']}"
            if t.get("payment_format"):
                line += f", {t['payment_format']}"
            lines.append(line)
    lines.append("")
    lines.append(
        "Accounts (label = bank_id/account, jurisdiction; step from the seed; "
        "number of distinct accounts that pay it and that it pays in the window):"
    )
    for acc, alias in b.aliases.items():
        i = b.info[acc]
        where = (
            "seed"
            if i["hop"] == 0
            else ("found by trace" if i["hop"] == "trace" else f"step {i['hop']}")
        )
        degree = (
            f"paid by {i['senders']}, pays {i['receivers']}"
            if "senders" in i
            else "degree not looked up"
        )
        lines.append(f"{alias} = {acc[0]}/{acc[1]} {i.get('jurisdiction', '')}; {where}; {degree}")
    lines.append("")
    lines.append(
        "Transfers in the window (sender -> receiver: count, totals per currency, first to last):"
    )
    for n, ((src, dst), e) in enumerate(b.edges.items()):
        if n >= MAX_TRANSFER_LINES:
            lines.append(f"... {len(b.edges) - MAX_TRANSFER_LINES} more pairs not shown")
            break
        when = e["first"] if e["first"] == e["last"] else f"{e['first']} to {e['last']}"
        one_off = " [one-off]" if e["n_tx"] <= ONE_OFF_MAX_TRANSFERS else ""
        lines.append(
            f"{b.aliases[src]} -> {b.aliases[dst]}: {e['n_tx']} tx, {_totals(e['totals'])}, "
            f"{when}{one_off}"
        )
    lines.append("")
    if trips:
        lines.append(
            "Loops through the seed (traces up to 8 steps each way; each transfer is listed "
            "in money-flow order, times can wrap around the seed):"
        )
        for path in trips:
            hops = ", ".join(
                f"{b.aliases[_src(e)]} -> {b.aliases[_dst(e)]} {e['ts']}" for e in path
            )
            lines.append(f"{len(path)} transfers: {hops}")
    else:
        lines.append("Loops through the seed (traces up to 8 steps each way): none found.")
    if not_expanded:
        busy = ", ".join(b.aliases[a] for a in not_expanded)
        lines.append(
            f"Not expanded (busy accounts with more than {EXPAND_MAX_DEGREE} counterparties, "
            f"or limit reached): {busy}."
        )
    if step1 and step1.get("truncated"):
        lines.append("The seed has more counterparties than shown.")

    graph = {
        "nodes": [
            {
                "label": alias,
                "bank_id": acc[0],
                "account": acc[1],
                **{k: b.info[acc].get(k) for k in ("hop", "senders", "receivers", "jurisdiction")},
            }
            for acc, alias in b.aliases.items()
        ],
        "edges": [
            {"src": b.aliases[src], "dst": b.aliases[dst], **e} for (src, dst), e in b.edges.items()
        ],
        "loops": [
            [
                {
                    "tx_id": e["tx_id"],
                    "src": b.aliases[_src(e)],
                    "dst": b.aliases[_dst(e)],
                    "ts": e["ts"],
                }
                for e in path
            ]
            for path in trips
        ],
    }
    candidates = find_candidates(graph)
    lines.append("")
    lines.append(describe(candidates))

    # Behavioral risk: the subject and its first-time step-1 counterparties.
    behavior = {"A0": await call("get_account_behavior", base)}
    first_time = sorted(
        (
            (c["n_tx"], c["bank_id"], c["account"])
            for c in (step1 or {}).get("counterparties", [])
            if c["n_tx"] <= ONE_OFF_MAX_TRANSFERS
        ),
    )
    checked: set[Account] = set()
    for _, bank, acct in first_time:
        if (bank, acct) in checked or len(checked) >= risk_rules.MAX_RISK_COUNTERPARTIES:
            continue
        checked.add((bank, acct))
        behavior[b.aliases[(bank, acct)]] = await call(
            "get_account_behavior", {"bank_id": bank, "account": acct, **window}
        )
    subject_signals = (behavior["A0"] or {}).get("signals", {})
    case_risk = risk_rules.case_risk(
        subject_signals,
        {k: v["signals"] for k, v in behavior.items() if k != "A0" and v},
    )
    lines.append("")
    lines.append(risk_rules.describe(case_risk))
    return CaseFile(
        text="\n".join(lines),
        graph=graph,
        candidates=[c.as_dict() for c in candidates],
        risk=case_risk,
        aliases={alias: acc for acc, alias in b.aliases.items()},
        seen_tx_ids=list(dict.fromkeys(b.tx_ids)),
        seen_accounts=list(b.aliases),
        tool_log=log,
        triggers=[
            {
                **t,
                "from_label": b.aliases[(t["from_bank"], t["from_account"])],
                "to_label": b.aliases[(t["to_bank"], t["to_account"])],
            }
            for t in triggers
        ],
    )


def resolve_accounts(
    names: list[Any], aliases: dict[str, Account], known: set[Account]
) -> tuple[list[Account], list[str]]:
    """Map the model's account names (labels, "bank/account" or objects) to accounts.

    Accounts that no tool returned during the case are dropped and reported.
    """
    out: list[Account] = []
    problems: list[str] = []
    for name in names:
        acc: Account | None = None
        if isinstance(name, dict) and "bank_id" in name and "account" in name:
            acc = (int(name["bank_id"]), str(name["account"]))
        elif isinstance(name, str):
            text = name.strip().split()[0] if name.strip() else ""
            if m := ALIAS_RE.match(text):
                acc = aliases.get(f"A{int(m.group(1))}")
            elif m := DIRECT_RE.match(name.strip()):
                acc = (int(m.group(1)), m.group(2))
        if acc is None:
            problems.append(f"unknown account name {name!r}")
        elif acc not in known:
            problems.append(f"account {acc[0]}/{acc[1]} was never returned by a tool")
        elif acc not in out:
            out.append(acc)
    return out, problems
