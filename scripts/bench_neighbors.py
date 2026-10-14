"""Tool-query latency: p50/p95/p99 of neighbor lookups over the full transactions table.

Each lookup returns one account's non-self transactions (both directions) inside a
2-day window, as the Sprint 1 `get_neighbors` tool will. Accounts are a seeded
random sample. Target: p95 under 1 second (PRD section 6).
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from datetime import timedelta

from aml_agent.data.views import connect

NEIGHBOR_SQL = """
    SELECT tx_id, ts, from_bank, from_account, to_bank, to_account,
           amount_paid, currency_paid, payment_format
    FROM transactions
    WHERE NOT is_self_transfer AND ts BETWEEN ? AND ?
      AND ((from_bank = ? AND from_account = ?) OR (to_bank = ? AND to_account = ?))
    ORDER BY ts, tx_id
    LIMIT 500
"""


def run(n: int, seed: int, mode: str) -> dict:
    con = connect(["transactions"])
    if mode == "memory":
        con.execute("CREATE TABLE tx_mem AS SELECT * FROM transactions")
        con.execute("DROP VIEW transactions")
        con.execute("ALTER TABLE tx_mem RENAME TO transactions")
    # Sample parameters cannot be bound; both are validated ints.
    accounts = con.execute(
        f"SELECT from_bank, from_account, ts FROM transactions "
        f"USING SAMPLE reservoir({int(n)} ROWS) REPEATABLE ({int(seed)})"
    ).fetchall()
    rng = random.Random(seed)
    rng.shuffle(accounts)
    timings = []
    for bank, account, ts in accounts:
        start, end = ts - timedelta(days=1), ts + timedelta(days=1)
        t0 = time.perf_counter()
        con.execute(NEIGHBOR_SQL, [start, end, bank, account, bank, account]).fetchall()
        timings.append(time.perf_counter() - t0)
    q = statistics.quantiles(timings, n=100)
    return {
        "mode": mode,
        "lookups": len(timings),
        "p50_ms": round(q[49] * 1000, 1),
        "p95_ms": round(q[94] * 1000, 1),
        "p99_ms": round(q[98] * 1000, 1),
        "max_ms": round(max(timings) * 1000, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--mode", choices=["parquet", "memory"], default="parquet")
    args = parser.parse_args()
    print(json.dumps(run(args.n, args.seed, args.mode)))


if __name__ == "__main__":
    main()
