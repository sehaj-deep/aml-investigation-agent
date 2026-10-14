"""Read-only, bounded transaction-graph tools (FR-2).

Every tool:
- opens nothing itself; it uses one DuckDB connection opened with read_only=True
  on the tool database (no labels, no pattern tables);
- validates arguments with Pydantic (malformed arguments are rejected);
- caps hops, rows and windows, and reports any cap it applied in `capped`;
- reports amounts per currency and never sums across currencies;
- hides self-transfers unless asked, and reports how many were hidden;
- shows what an analyst sees: every date and the payment format. Both are unusually
  predictive in this simulator (rows after Sep 10 are mostly laundering, and most
  laundering is ACH), so each can be hidden for a comparison run
  (TOOLS_SHOW_LATE_ROWS=false clips to 2022-09-10 23:59, TOOLS_SHOW_PAYMENT_FORMAT=false).
Amounts are returned as strings so no precision is lost.
"""

from __future__ import annotations

import bisect
import os
import statistics
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from aml_agent.analysis.risk import account_score, fired_rules
from aml_agent.data.tooldb import tool_db_path

MAX_HOPS = 8  # chain patterns (cycle, random) reach up to 8 steps from the seed on dev alerts
MAX_COUNTERPARTIES = 100
DEFAULT_COUNTERPARTIES = 25
MAX_TX_IDS_PER_COUNTERPARTY = 20
MAX_TRACE_EDGES = 300
MAX_FANOUT_PER_NODE = 20
MAX_TX_IDS = 100
MAX_BEHAVIOR_TRANSFERS = 5000
MAX_WINDOW = timedelta(days=31)
MAX_GROUP_ACCOUNTS = 30
MAX_GROUP_TRANSFERS = 300
DATA_START = datetime(2022, 9, 1)
PRIMARY_PERIOD_END = datetime(2022, 9, 10, 23, 59)  # last minute shown by default
FULL_DATA_END = datetime(2022, 9, 19)

ACCOUNT_PATTERN = r"^[0-9A-Z]{1,20}$"


def show_late_rows() -> bool:
    """Rows after Sep 10 are mostly laundering in this simulator. On by default."""
    return os.environ.get("TOOLS_SHOW_LATE_ROWS", "true").lower() == "true"


def data_end() -> datetime:
    return FULL_DATA_END if show_late_rows() else PRIMARY_PERIOD_END


def show_payment_format() -> bool:
    """Analysts see the payment format; it is unusually predictive here. On by default."""
    return os.environ.get("TOOLS_SHOW_PAYMENT_FORMAT", "true").lower() == "true"


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WindowArgs(_Args):
    window_start: datetime | None = None
    window_end: datetime | None = None

    @model_validator(mode="after")
    def _check_window(self) -> WindowArgs:
        if self.window_start and self.window_end and self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        return self


class AccountArgs(WindowArgs):
    bank_id: int = Field(ge=0, le=10_000_000)
    account: str = Field(pattern=ACCOUNT_PATTERN)


class SummaryArgs(AccountArgs):
    pass


# Models mix up the two direction vocabularies, so each tool accepts both and
# normalizes: in = backward (money arriving), out = forward (money leaving).
NEIGHBOR_DIRECTIONS = {"in": "in", "backward": "in", "out": "out", "forward": "out", "both": "both"}
TRACE_DIRECTIONS = {
    "forward": "forward",
    "out": "forward",
    "backward": "backward",
    "in": "backward",
}


class NeighborArgs(AccountArgs):
    direction: Literal["in", "out", "both", "forward", "backward"] = "both"
    limit: int = Field(default=DEFAULT_COUNTERPARTIES, ge=1)
    include_self_transfers: bool = False


class TraceArgs(AccountArgs):
    direction: Literal["forward", "backward", "out", "in"] = "forward"
    hops: int = Field(default=2, ge=1)
    max_edges: int = Field(default=100, ge=1)


class AccountRef(_Args):
    bank_id: int = Field(ge=0, le=10_000_000)
    account: str = Field(pattern=ACCOUNT_PATTERN)


class AmongArgs(WindowArgs):
    accounts: list[AccountRef] = Field(min_length=2)
    limit: int = Field(default=200, ge=1)


class TransactionsArgs(_Args):
    tx_ids: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def _positive(self) -> TransactionsArgs:
        if any(t < 1 for t in self.tx_ids):
            raise ValueError("tx_ids must be positive")
        return self


def _amount(value: Decimal) -> str:
    return format(value, "f")


def _ts(value: datetime | None) -> str | None:
    return value.isoformat(timespec="minutes") if value else None


class GraphTools:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or tool_db_path()
        self.con = duckdb.connect(str(self.db_path), read_only=True)
        self.con.execute("SET enable_progress_bar = false")

    def close(self) -> None:
        self.con.close()

    # Helpers

    def _window(self, args: WindowArgs, capped: dict) -> tuple[datetime, datetime]:
        last = data_end()
        start = args.window_start or DATA_START
        end = args.window_end or last
        start, end = max(start, DATA_START), min(end, last)
        if end <= start:
            raise ValueError(f"window lies outside the data ({_ts(DATA_START)} to {_ts(last)})")
        if end - start > MAX_WINDOW:
            capped["window_end"] = {"requested": _ts(end), "applied": _ts(start + MAX_WINDOW)}
            end = start + MAX_WINDOW
        return start, end

    def _bank(self, bank_id: int) -> dict[str, Any]:
        row = self.con.execute(
            "SELECT bank_name, jurisdiction FROM banks WHERE bank_id = ?", [bank_id]
        ).fetchone()
        return {"bank_name": row[0], "jurisdiction": row[1]} if row else {}

    def _degrees(
        self, accounts: list[tuple[int, str]], start: datetime, end: datetime
    ) -> dict[tuple[int, str], dict[str, int]]:
        """Distinct senders and receivers of each account in the window (no self-transfers)."""
        out = {acc: {"their_senders": 0, "their_receivers": 0} for acc in accounts}
        if not accounts:
            return out
        params = {
            "banks": [b for b, _ in accounts],
            "accts": [a for _, a in accounts],
            "start": start,
            "end": end,
        }
        for key, here_b, here_a, there_b, there_a in (
            ("their_receivers", "from_bank", "from_account", "to_bank", "to_account"),
            ("their_senders", "to_bank", "to_account", "from_bank", "from_account"),
        ):
            rows = self.con.execute(
                f"""
                WITH cp AS (SELECT DISTINCT unnest($banks) AS b, unnest($accts) AS a)
                SELECT t.{here_b}, t.{here_a}, count(DISTINCT (t.{there_b}, t.{there_a}))
                FROM transactions t JOIN cp ON t.{here_b} = cp.b AND t.{here_a} = cp.a
                WHERE NOT t.is_self_transfer AND t.ts BETWEEN $start AND $end
                GROUP BY 1, 2
                """,
                params,
            ).fetchall()
            for b, a, n in rows:
                out[(b, a)][key] = n
        return out

    @staticmethod
    def _cap(capped: dict, name: str, requested: int, limit: int) -> int:
        if requested > limit:
            capped[name] = {"requested": requested, "applied": limit}
            return limit
        return requested

    # Tools

    def get_account_summary(self, **kwargs: Any) -> dict[str, Any]:
        """Per-currency sent and received counts and totals, counterparties and time span."""
        args = SummaryArgs(**kwargs)
        capped: dict = {}
        start, end = self._window(args, capped)
        key = [args.bank_id, args.account]
        base = "NOT is_self_transfer AND ts BETWEEN ? AND ?"
        sent = self.con.execute(
            f"""SELECT currency_paid, count(*), sum(amount_paid) FROM transactions
                WHERE from_bank = ? AND from_account = ? AND {base}
                GROUP BY 1 ORDER BY 1""",
            [*key, start, end],
        ).fetchall()
        received = self.con.execute(
            f"""SELECT currency_received, count(*), sum(amount_received) FROM transactions
                WHERE to_bank = ? AND to_account = ? AND {base}
                GROUP BY 1 ORDER BY 1""",
            [*key, start, end],
        ).fetchall()
        n_out, n_in, first_ts, last_ts, hidden = self.con.execute(
            """
            SELECT
                count(DISTINCT (to_bank, to_account)) FILTER (
                    WHERE from_bank = ? AND from_account = ? AND NOT is_self_transfer),
                count(DISTINCT (from_bank, from_account)) FILTER (
                    WHERE to_bank = ? AND to_account = ? AND NOT is_self_transfer),
                min(ts) FILTER (WHERE NOT is_self_transfer),
                max(ts) FILTER (WHERE NOT is_self_transfer),
                count(*) FILTER (WHERE is_self_transfer)
            FROM transactions
            WHERE ts BETWEEN ? AND ?
              AND ((from_bank = ? AND from_account = ?) OR (to_bank = ? AND to_account = ?))
            """,
            [*key, *key, start, end, *key, *key],
        ).fetchone()
        return {
            "account": {
                "bank_id": args.bank_id,
                "account": args.account,
                **self._bank(args.bank_id),
            },
            "window": {"start": _ts(start), "end": _ts(end)},
            "found": bool(sent or received or hidden),
            "sent": [{"currency": c, "n_tx": n, "total": _amount(t)} for c, n, t in sent],
            "received": [{"currency": c, "n_tx": n, "total": _amount(t)} for c, n, t in received],
            "counterparties_out": n_out,
            "counterparties_in": n_in,
            "first_ts": _ts(first_ts),
            "last_ts": _ts(last_ts),
            "self_transfers_hidden": hidden,
            "capped": capped,
        }

    def get_neighbors(self, **kwargs: Any) -> dict[str, Any]:
        """Counterparties of an account in a window, with per-currency totals and tx_ids."""
        args = NeighborArgs(**kwargs)
        direction = NEIGHBOR_DIRECTIONS[args.direction]
        capped: dict = {}
        start, end = self._window(args, capped)
        limit = self._cap(capped, "limit", args.limit, MAX_COUNTERPARTIES)
        self_filter = "" if args.include_self_transfers else "AND NOT is_self_transfer"
        legs = []
        if direction in ("out", "both"):
            legs.append(
                f"""SELECT 'out' AS direction, to_bank AS cp_bank, to_account AS cp_account,
                       tx_id, ts, currency_paid AS currency, amount_paid AS amount
                    FROM transactions WHERE from_bank = $bank AND from_account = $acct
                      AND ts BETWEEN $start AND $end {self_filter}"""
            )
        if direction in ("in", "both"):
            legs.append(
                f"""SELECT 'in' AS direction, from_bank AS cp_bank, from_account AS cp_account,
                       tx_id, ts, currency_received AS currency, amount_received AS amount
                    FROM transactions WHERE to_bank = $bank AND to_account = $acct
                      AND ts BETWEEN $start AND $end {self_filter}"""
            )
        rows = self.con.execute(
            f"""
            WITH legs AS ({" UNION ALL ".join(legs)}),
            per_currency AS (
                SELECT direction, cp_bank, cp_account, currency,
                       sum(amount) AS total, count(*) AS n
                FROM legs GROUP BY ALL
            ),
            per_cp AS (
                SELECT direction, cp_bank, cp_account, count(*) AS n_tx,
                       min(ts) AS first_ts, max(ts) AS last_ts,
                       list(tx_id ORDER BY ts, tx_id) AS tx_ids
                FROM legs GROUP BY ALL
            )
            SELECT p.direction, p.cp_bank, p.cp_account, p.n_tx, p.first_ts, p.last_ts,
                   p.tx_ids,
                   (SELECT list({{'currency': c.currency, 'n_tx': c.n, 'total': c.total}}
                                ORDER BY c.currency)
                    FROM per_currency c
                    WHERE c.direction = p.direction AND c.cp_bank = p.cp_bank
                      AND c.cp_account = p.cp_account) AS totals,
                   count(*) OVER () AS total_counterparties
            FROM per_cp p
            ORDER BY p.n_tx DESC, p.direction, p.cp_bank, p.cp_account
            LIMIT $limit
            """,
            {
                "bank": args.bank_id,
                "acct": args.account,
                "start": start,
                "end": end,
                "limit": limit,
            },
        ).fetchall()
        total = rows[0][8] if rows else 0
        degrees = self._degrees([(r[1], r[2]) for r in rows], start, end)
        counterparties = []
        for leg, cp_bank, cp_account, n_tx, first_ts, last_ts, tx_ids, totals, _ in rows:
            counterparties.append(
                {
                    "direction": leg,
                    "bank_id": cp_bank,
                    "account": cp_account,
                    **self._bank(cp_bank),
                    "n_tx": n_tx,
                    "totals": [
                        {"currency": t["currency"], "n_tx": t["n_tx"], "total": _amount(t["total"])}
                        for t in totals
                    ],
                    "first_ts": _ts(first_ts),
                    "last_ts": _ts(last_ts),
                    "tx_ids": tx_ids[:MAX_TX_IDS_PER_COUNTERPARTY],
                    "tx_ids_truncated": len(tx_ids) > MAX_TX_IDS_PER_COUNTERPARTY,
                    # How many distinct accounts this counterparty itself pays and is paid
                    # by in the window: a large number marks a hub worth following.
                    **degrees[(cp_bank, cp_account)],
                }
            )
        return {
            "account": {"bank_id": args.bank_id, "account": args.account},
            "window": {"start": _ts(start), "end": _ts(end)},
            "direction": direction,
            "counterparties": counterparties,
            "total_counterparties": total,
            "truncated": total > len(counterparties),
            "capped": capped,
        }

    def trace_funds(self, **kwargs: Any) -> dict[str, Any]:
        """Bounded multi-hop tracing. Forward follows money out of each account no earlier
        than it arrived; backward follows money in no later than it left."""
        args = TraceArgs(**kwargs)
        capped: dict = {}
        start, end = self._window(args, capped)
        hops = self._cap(capped, "hops", args.hops, MAX_HOPS)
        max_edges = self._cap(capped, "max_edges", args.max_edges, MAX_TRACE_EDGES)
        direction = TRACE_DIRECTIONS[args.direction]
        forward = direction == "forward"
        here_bank, here_acct, there_bank, there_acct = (
            ("from_bank", "from_account", "to_bank", "to_account")
            if forward
            else ("to_bank", "to_account", "from_bank", "from_account")
        )
        time_cond = "t.ts >= f.t" if forward else "t.ts <= f.t"
        frontier = [(args.bank_id, args.account, start if forward else end)]
        visited = {(args.bank_id, args.account)}
        edges: list[dict] = []
        truncated = False
        for hop in range(1, hops + 1):
            if not frontier or len(edges) >= max_edges:
                break
            rows = self.con.execute(
                f"""
                WITH f AS (
                    SELECT unnest($banks) AS bank, unnest($accts) AS acct, unnest($times) AS t)
                SELECT t.tx_id, t.ts, t.from_bank, t.from_account, t.to_bank, t.to_account,
                       t.amount_paid, t.currency_paid, t.amount_received, t.currency_received
                FROM transactions t JOIN f
                  ON t.{here_bank} = f.bank AND t.{here_acct} = f.acct AND {time_cond}
                WHERE NOT t.is_self_transfer AND t.ts BETWEEN $start AND $end
                QUALIFY row_number() OVER (
                    PARTITION BY t.{here_bank}, t.{here_acct}
                    ORDER BY t.ts {"ASC" if forward else "DESC"}, t.tx_id) <= $fanout
                ORDER BY t.ts, t.tx_id
                """,
                {
                    "banks": [b for b, _, _ in frontier],
                    "accts": [a for _, a, _ in frontier],
                    "times": [t for _, _, t in frontier],
                    "start": start,
                    "end": end,
                    "fanout": MAX_FANOUT_PER_NODE,
                },
            ).fetchall()
            next_frontier: dict[tuple[int, str], datetime] = {}
            seen_tx = {e["tx_id"] for e in edges}
            for tx_id, ts, fb, fa, tb, ta, ap, cp, ar, cr in rows:
                if tx_id in seen_tx:
                    continue
                if len(edges) >= max_edges:
                    truncated = True
                    break
                edges.append(
                    {
                        "hop": hop,
                        "tx_id": tx_id,
                        "ts": _ts(ts),
                        "from_bank": fb,
                        "from_account": fa,
                        "to_bank": tb,
                        "to_account": ta,
                        "amount_paid": _amount(ap),
                        "currency_paid": cp,
                        "amount_received": _amount(ar),
                        "currency_received": cr,
                    }
                )
                nxt = (tb, ta) if forward else (fb, fa)
                if nxt not in visited:
                    # Forward: money can move on after it first arrives (earliest ts).
                    # Backward: money must arrive before it last leaves (latest ts).
                    prev = next_frontier.get(nxt)
                    if prev is None:
                        next_frontier[nxt] = ts
                    else:
                        next_frontier[nxt] = min(prev, ts) if forward else max(prev, ts)
            visited.update(next_frontier)
            frontier = [(b, a, t) for (b, a), t in sorted(next_frontier.items())]
        return {
            "start": {"bank_id": args.bank_id, "account": args.account},
            "direction": direction,
            "window": {"start": _ts(start), "end": _ts(end)},
            "hops_requested": args.hops,
            "hops_applied": hops,
            "edges": edges,
            "accounts_reached": len(visited) - 1,
            "truncated": truncated or len(edges) >= max_edges,
            "capped": capped,
        }

    def get_transfers_among(self, **kwargs: Any) -> dict[str, Any]:
        """Transfers whose sender AND receiver are both in a chosen group of accounts.

        Use it once the suspected pattern's accounts are known: the result is the
        pattern's structure without the accounts' unrelated activity.
        """
        args = AmongArgs(**kwargs)
        capped: dict = {}
        start, end = self._window(args, capped)
        group = list(dict.fromkeys((a.bank_id, a.account) for a in args.accounts))
        if len(group) > MAX_GROUP_ACCOUNTS:
            capped["accounts"] = {"requested": len(group), "applied": MAX_GROUP_ACCOUNTS}
            group = group[:MAX_GROUP_ACCOUNTS]
        limit = self._cap(capped, "limit", args.limit, MAX_GROUP_TRANSFERS)
        rows = self.con.execute(
            """
            WITH g AS (SELECT unnest($banks) AS b, unnest($accts) AS a)
            SELECT t.tx_id, t.ts, t.from_bank, t.from_account, t.to_bank, t.to_account,
                   t.amount_paid, t.currency_paid, t.amount_received, t.currency_received,
                   count(*) OVER () AS total
            FROM transactions t
            JOIN g s ON t.from_bank = s.b AND t.from_account = s.a
            JOIN g r ON t.to_bank = r.b AND t.to_account = r.a
            WHERE NOT t.is_self_transfer AND t.ts BETWEEN $start AND $end
            ORDER BY t.ts, t.tx_id
            LIMIT $limit
            """,
            {
                "banks": [b for b, _ in group],
                "accts": [a for _, a in group],
                "start": start,
                "end": end,
                "limit": limit,
            },
        ).fetchall()
        total = rows[0][10] if rows else 0
        transfers = [
            {
                "tx_id": r[0],
                "ts": _ts(r[1]),
                "from_bank": r[2],
                "from_account": r[3],
                "to_bank": r[4],
                "to_account": r[5],
                "amount_paid": _amount(r[6]),
                "currency_paid": r[7],
                "amount_received": _amount(r[8]),
                "currency_received": r[9],
            }
            for r in rows
        ]
        linked = {(t["from_bank"], t["from_account"]) for t in transfers} | {
            (t["to_bank"], t["to_account"]) for t in transfers
        }
        return {
            "window": {"start": _ts(start), "end": _ts(end)},
            "accounts": len(group),
            "transfers": transfers,
            "total_transfers": total,
            "truncated": total > len(transfers),
            # Group accounts with no transfer to or from another group member.
            "unconnected_accounts": [
                {"bank_id": b, "account": a} for b, a in group if (b, a) not in linked
            ],
            "capped": capped,
        }

    def get_account_behavior(self, **kwargs: Any) -> dict[str, Any]:
        """Behavioral red-flag signals for one account in a review period, with the risk
        rules they fire (aml_agent/analysis/risk.py). Non-self transfers only."""
        args = SummaryArgs(**kwargs)
        capped: dict = {}
        start, end = self._window(args, capped)
        key = [args.bank_id, args.account]
        rows = self.con.execute(
            f"""
            SELECT ts, from_bank, from_account, to_bank, to_account, currency_paid,
                   currency_received
            FROM transactions
            WHERE NOT is_self_transfer AND ts BETWEEN ? AND ?
              AND ((from_bank = ? AND from_account = ?) OR (to_bank = ? AND to_account = ?))
            ORDER BY ts, tx_id
            LIMIT {MAX_BEHAVIOR_TRANSFERS + 1}
            """,
            [start, end, *key, *key],
        ).fetchall()
        if len(rows) > MAX_BEHAVIOR_TRANSFERS:
            capped["transfers"] = {"applied": MAX_BEHAVIOR_TRANSFERS}
            rows = rows[:MAX_BEHAVIOR_TRANSFERS]
        acc = (args.bank_id, args.account)
        ins = [r for r in rows if (r[3], r[4]) == acc]
        outs = [r for r in rows if (r[1], r[2]) == acc]
        out_times = [r[0] for r in outs]
        onward_hours = []
        for r in ins:
            i = bisect.bisect_left(out_times, r[0])
            if i < len(out_times):
                onward_hours.append((out_times[i] - r[0]).total_seconds() / 3600)
        pair_n: dict[tuple, int] = {}
        for r in rows:
            other = (r[3], r[4]) if (r[1], r[2]) == acc else (r[1], r[2])
            pair_n[other] = pair_n.get(other, 0) + 1
        before = {
            (b, a)
            for b, a in self.con.execute(
                """
                SELECT DISTINCT
                    CASE WHEN from_bank = ? AND from_account = ? THEN to_bank ELSE from_bank END,
                    CASE WHEN from_bank = ? AND from_account = ?
                         THEN to_account ELSE from_account END
                FROM transactions
                WHERE NOT is_self_transfer AND ts >= ? AND ts < ?
                  AND ((from_bank = ? AND from_account = ?) OR (to_bank = ? AND to_account = ?))
                """,
                [*key, *key, DATA_START, start, *key, *key],
            ).fetchall()
        }
        (total,) = self.con.execute(
            """
            SELECT count(*) FROM transactions
            WHERE NOT is_self_transfer AND ts BETWEEN ? AND ?
              AND ((from_bank = ? AND from_account = ?) OR (to_bank = ? AND to_account = ?))
            """,
            [DATA_START, data_end(), *key, *key],
        ).fetchone()
        in_ccy = sorted({r[6] for r in ins})
        out_ccy = sorted({r[5] for r in outs})
        n_cp = len(pair_n)
        signals = {
            "n_transfers": len(rows),
            "n_in": len(ins),
            "n_out": len(outs),
            "n_counterparties": n_cp,
            "receives_and_pays": bool(ins) and bool(outs),
            "in_currencies": in_ccy,
            "out_currencies": out_ccy,
            "currency_switch": bool(in_ccy and out_ccy and not set(in_ccy) & set(out_ccy)),
            "new_counterparty_share": round(sum(1 for k in pair_n if k not in before) / n_cp, 4)
            if n_cp
            else 0.0,
            "one_time_counterparty_share": round(
                sum(1 for v in pair_n.values() if v <= 2) / n_cp, 4
            )
            if n_cp
            else 0.0,
            "period_activity_share": round(len(rows) / total, 4) if total else 0.0,
            "onward_within_24h_share": round(sum(1 for h in onward_hours if h <= 24) / len(ins), 4)
            if ins
            else 0.0,
            "median_hours_to_onward": round(statistics.median(onward_hours), 1)
            if onward_hours
            else None,
        }
        rules = fired_rules(signals)
        return {
            "account": {"bank_id": args.bank_id, "account": args.account},
            "window": {"start": _ts(start), "end": _ts(end)},
            "signals": signals,
            "rules": rules,
            "score": account_score(rules),
            "capped": capped,
        }

    def get_transactions(self, **kwargs: Any) -> dict[str, Any]:
        """Raw transaction records by tx_id (at most 100 per call)."""
        args = TransactionsArgs(**kwargs)
        capped: dict = {}
        ids = list(dict.fromkeys(args.tx_ids))
        if len(ids) > MAX_TX_IDS:
            capped["tx_ids"] = {"requested": len(ids), "applied": MAX_TX_IDS}
            ids = ids[:MAX_TX_IDS]
        fmt = ", payment_format" if show_payment_format() else ""
        rows = self.con.execute(
            f"""
            SELECT t.tx_id, t.ts, t.from_bank, fb.bank_name, t.from_account,
                   t.to_bank, tb.bank_name, t.to_account, t.amount_paid, t.currency_paid,
                   t.amount_received, t.currency_received{fmt}
            FROM transactions t
            LEFT JOIN banks fb ON fb.bank_id = t.from_bank
            LEFT JOIN banks tb ON tb.bank_id = t.to_bank
            WHERE t.tx_id IN (SELECT unnest(?)) AND t.ts <= ?
            ORDER BY t.tx_id
            """,
            [ids, data_end()],
        ).fetchall()
        records = []
        for r in rows:
            rec = {
                "tx_id": r[0],
                "timestamp": _ts(r[1]),
                "from_bank": r[2],
                "from_bank_name": r[3],
                "from_account": r[4],
                "to_bank": r[5],
                "to_bank_name": r[6],
                "to_account": r[7],
                "amount_paid": _amount(r[8]),
                "currency_paid": r[9],
                "amount_received": _amount(r[10]),
                "currency_received": r[11],
            }
            if fmt:
                rec["payment_format"] = r[12]
            records.append(rec)
        found = {r["tx_id"] for r in records}
        return {
            "transactions": records,
            "not_found": [i for i in ids if i not in found],
            "capped": capped,
        }
