"""Seeded generation of the dev and evaluation alert sets (PRD section 10).

Positives: per pattern type, draw blocks from the seed-eligible multi-row blocks
that finish within the primary period (by 2022-09-10), 3 dev and 5 eval. The
dataset author notes that the days after Sep 10 hold only laundering, so patterns
running past it would be incomplete or give the answer away. The seed is a seeded
draw from that block's eligible accounts. The window is the block's span padded
on both sides and clipped to the primary period.

Benign controls: one per positive. The seed is an account in no labeled row,
in the same activity bucket as the positive's seed (non-self transactions and
distinct counterparties, log2 buckets), and with at least one non-self
transaction inside the positive's window, which it reuses. So window dates
cannot reveal the label.

Alert IDs are assigned after shuffling positives and controls together, so an
ID says nothing about the label.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import duckdb

from aml_agent.alerts.models import Alert, GroundTruth

PRIMARY_PERIOD_END = datetime(2022, 9, 11)  # rows at or after this are the tail
LAST_PRIMARY_MINUTE = PRIMARY_PERIOD_END - timedelta(minutes=1)
WINDOW_PADDING = timedelta(hours=24)
DEV_PER_TYPE = 3
EVAL_PER_TYPE = 5


@dataclass
class AlertSet:
    name: str
    alerts: list[Alert] = field(default_factory=list)
    truth: list[GroundTruth] = field(default_factory=list)


def _bucket(n_tx: int, degree: int) -> tuple[int, int]:
    return (int(math.log2(max(n_tx, 1))), int(math.log2(max(degree, 1))))


def _activity_sql(where: str = "TRUE") -> str:
    """Non-self activity per account: transaction count and distinct counterparties."""
    return f"""
        WITH legs AS (
            SELECT from_bank AS bank_id, from_account AS account,
                   to_bank AS cp_bank, to_account AS cp_account
            FROM transactions WHERE NOT is_self_transfer AND ts < '2022-09-11'
            UNION ALL
            SELECT to_bank, to_account, from_bank, from_account
            FROM transactions WHERE NOT is_self_transfer AND ts < '2022-09-11'
        )
        SELECT bank_id, account, count(*) AS n_tx,
               count(DISTINCT (cp_bank, cp_account)) AS degree
        FROM legs WHERE {where}
        GROUP BY bank_id, account
    """


def _labeled_accounts_sql() -> str:
    return """
        SELECT from_bank AS bank_id, from_account AS account FROM transactions
        WHERE is_laundering
        UNION
        SELECT to_bank, to_account FROM transactions WHERE is_laundering
    """


def generate(
    con: duckdb.DuckDBPyConnection,
    seed: int,
    dev_per_type: int = DEV_PER_TYPE,
    eval_per_type: int = EVAL_PER_TYPE,
    padding: timedelta = WINDOW_PADDING,
) -> dict[str, AlertSet]:
    """Build the dev and eval sets. `con` needs the Parquet tables as views."""
    rng = random.Random(seed)

    blocks = con.execute(
        """
        SELECT DISTINCT b.block_id, b.pattern_type, b.first_ts, b.last_ts
        FROM pattern_blocks b JOIN seed_eligible s USING (block_id)
        WHERE b.last_ts < ?
        ORDER BY b.pattern_type, b.block_id
        """,
        [PRIMARY_PERIOD_END],
    ).fetchall()
    by_type: dict[str, list[tuple]] = {}
    for row in blocks:
        by_type.setdefault(row[1], []).append(row)

    eligible: dict[int, list[tuple[int, str]]] = {}
    for block_id, bank_id, account in con.execute(
        "SELECT block_id, bank_id, account FROM seed_eligible ORDER BY ALL"
    ).fetchall():
        eligible.setdefault(block_id, []).append((bank_id, account))

    positives: dict[str, list[dict]] = {"dev": [], "eval": []}
    for ptype in sorted(by_type):
        chosen = rng.sample(by_type[ptype], dev_per_type + eval_per_type)
        for i, (block_id, _, first_ts, last_ts) in enumerate(chosen):
            bank_id, account = rng.choice(eligible[block_id])
            positives["dev" if i < dev_per_type else "eval"].append(
                {
                    "block_id": block_id,
                    "pattern_type": ptype,
                    "seed": (bank_id, account),
                    "window": (first_ts - padding, min(last_ts + padding, LAST_PRIMARY_MINUTE)),
                    "late": last_ts >= PRIMARY_PERIOD_END,
                }
            )

    # Activity of every account with no labeled row (benign candidates), bucketed.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE benign_pool AS
        SELECT a.* FROM ({_activity_sql()}) a
        ANTI JOIN ({_labeled_accounts_sql()}) l
          ON l.bank_id = a.bank_id AND l.account = a.account
        """
    )
    pool: dict[tuple[int, int], list[tuple[int, str]]] = {}
    for bank_id, account, n_tx, degree in con.execute(
        "SELECT bank_id, account, n_tx, degree FROM benign_pool ORDER BY bank_id, account"
    ).fetchall():
        pool.setdefault(_bucket(n_tx, degree), []).append((bank_id, account))

    used: set[tuple[int, str]] = set()
    sets: dict[str, AlertSet] = {}
    for set_name in ("dev", "eval"):
        items: list[dict] = []
        for pos in positives[set_name]:
            items.append({**pos, "label": "positive"})
            benign_seed = _draw_benign(con, rng, pool, used, pos)
            used.add(benign_seed)
            items.append(
                {
                    "label": "benign",
                    "seed": benign_seed,
                    "window": pos["window"],
                    "late": pos["late"],
                    "matched_block": pos["block_id"],
                }
            )
        rng.shuffle(items)
        alert_set = AlertSet(set_name)
        ids = {id(item): f"{set_name}-{n:04d}" for n, item in enumerate(items, start=1)}
        block_to_id = {
            item["block_id"]: ids[id(item)] for item in items if item["label"] == "positive"
        }
        for item in items:
            alert_id = ids[id(item)]
            (bank_id, account), (start, end) = item["seed"], item["window"]
            alert_set.alerts.append(
                Alert(
                    alert_id=alert_id,
                    seed_bank=bank_id,
                    seed_account=account,
                    window_start=start,
                    window_end=end,
                )
            )
            if item["label"] == "positive":
                truth = GroundTruth(
                    alert_id=alert_id,
                    label="positive",
                    block_id=item["block_id"],
                    pattern_type=item["pattern_type"],
                    runs_past_primary_period=item["late"],
                )
            else:
                truth = GroundTruth(
                    alert_id=alert_id,
                    label="benign",
                    matched_to=block_to_id[item["matched_block"]],
                    runs_past_primary_period=item["late"],
                )
            alert_set.truth.append(truth)
        sets[set_name] = alert_set
    return sets


def _draw_benign(
    con: duckdb.DuckDBPyConnection,
    rng: random.Random,
    pool: dict[tuple[int, int], list[tuple[int, str]]],
    used: set[tuple[int, str]],
    pos: dict,
) -> tuple[int, str]:
    """Pick a benign seed in the positive seed's activity bucket, active in its window.

    If the exact bucket has no usable account, widen to the nearest buckets.
    """
    bank_id, account = pos["seed"]
    n_tx, degree = con.execute(
        f"SELECT n_tx, degree FROM ({_activity_sql('bank_id = ? AND account = ?')})",
        [bank_id, account],
    ).fetchone()
    target = _bucket(n_tx, degree)
    start, end = pos["window"]
    active = {
        (b, a)
        for b, a in con.execute(
            """
            SELECT from_bank, from_account FROM transactions
            WHERE NOT is_self_transfer AND ts BETWEEN ? AND ?
            UNION
            SELECT to_bank, to_account FROM transactions
            WHERE NOT is_self_transfer AND ts BETWEEN ? AND ?
            """,
            [start, end, start, end],
        ).fetchall()
    }
    ranked = sorted(pool, key=lambda b: (abs(b[0] - target[0]) + abs(b[1] - target[1]), b))
    for bucket in ranked:
        candidates = [c for c in pool[bucket] if c in active and c not in used]
        if candidates:
            return rng.choice(candidates)
    raise RuntimeError("no benign candidate found")
