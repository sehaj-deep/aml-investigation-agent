"""Scorecard part A: detection at the data's natural laundering rate (no model, no quota).

Every account active in a review period is scored with the risk rules
(aml_agent/analysis/population.py). An account is positive if it sends or receives
any labeled laundering transaction in that period (pattern or other laundering).
Accounts of the frozen evaluation set (alert seeds and every account of its pattern
blocks) are removed from the population, so this never touches that set.

Reports, per period: base rate, then for each case-score threshold the alerts raised,
recall, precision and alerts per true case, plus average precision (PR-AUC). Also a
transaction-level view on the late test period (sender or receiver flagged), in the
terms used by the dataset paper (minority-class F1), with the caveats in the scorecard.

    python evals/detection_eval.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from aml_agent import config
from aml_agent.alerts.io import read_alerts, read_truth
from aml_agent.analysis.population import score_population
from aml_agent.data.tooldb import tool_db_path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "evals" / "runs" / "detection"

ACCOUNT_PERIODS = [
    ("2022-09-04 to 09-06", datetime(2022, 9, 4), datetime(2022, 9, 6, 23, 59)),
    ("2022-09-07 to 09-09", datetime(2022, 9, 7), datetime(2022, 9, 9, 23, 59)),
]
# Test period of the dataset authors' 60/20/20 chronological split, primary period only.
TEST_PERIOD = (
    "test period 09-08 16:12 to 09-10",
    datetime(2022, 9, 8, 16, 12),
    datetime(2022, 9, 10, 23, 59),
)


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    con.execute(f"ATTACH '{tool_db_path().as_posix()}' AS src (READ_ONLY)")
    con.execute("CREATE VIEW transactions AS SELECT * FROM src.transactions")
    # Labels come from the Parquet source; the tool database has none.
    con.execute(
        "CREATE VIEW labels AS SELECT tx_id, is_laundering FROM "
        f"'{config.table_path('transactions').as_posix()}'"
    )
    con.execute(
        "CREATE VIEW pattern_accounts AS SELECT * FROM "
        f"'{config.table_path('pattern_accounts').as_posix()}'"
    )
    con.execute(
        "CREATE VIEW pattern_transactions AS SELECT * FROM "
        f"'{config.table_path('pattern_transactions').as_posix()}'"
    )
    return con


def excluded_accounts(con: duckdb.DuckDBPyConnection) -> None:
    eval_blocks = sorted({t.block_id for t in read_truth("eval") if t.block_id})
    seeds = [(a.seed_bank, a.seed_account) for a in read_alerts("eval")]
    con.execute(
        "CREATE OR REPLACE TEMP TABLE excluded AS "
        "SELECT DISTINCT bank_id AS b, account AS a FROM pattern_accounts "
        "WHERE block_id IN (SELECT unnest(?))",
        [eval_blocks],
    )
    con.executemany("INSERT INTO excluded VALUES (?, ?)", seeds)


def threshold_table(
    rows: list[tuple[int, bool]], subgroup: list[bool] | None = None
) -> tuple[list[dict], float, int, int]:
    """rows: (score, is_positive). Returns per-threshold metrics, AP, positives, total.

    `subgroup` marks positives of a subgroup (pattern laundering); its recall is added.
    """
    positives = sum(1 for _, y in rows if y)
    total = len(rows)
    table = []
    ap = 0.0
    prev_recall = 0.0
    for t in sorted({s for s, _ in rows if s > 0}, reverse=True):
        flagged = [y for s, y in rows if s >= t]
        tp = sum(flagged)
        recall = tp / positives if positives else 0.0
        precision = tp / len(flagged) if flagged else 0.0
        ap += (recall - prev_recall) * precision
        prev_recall = recall
        row_extra = {}
        if subgroup is not None:
            members = [i for i, g in enumerate(subgroup) if g]
            hit = sum(1 for i in members if rows[i][0] >= t)
            row_extra["recall_pattern_laundering"] = (
                round(hit / len(members), 4) if members else None
            )
        table.append(
            {
                **row_extra,
                "threshold": t,
                "alerts": len(flagged),
                "true_cases": tp,
                "recall": round(recall, 4),
                "precision": round(precision, 4),
                "alerts_per_true_case": round(len(flagged) / tp, 1) if tp else None,
                "alert_rate": round(len(flagged) / total, 5),
            }
        )
    return sorted(table, key=lambda r: r["threshold"]), round(ap, 4), positives, total


def account_level(con, name: str, start: datetime, end: datetime) -> dict:
    score_population(con, start, end)
    rows = con.execute(
        """
        WITH pos AS (
            SELECT DISTINCT b, a FROM (
                SELECT t.from_bank AS b, t.from_account AS a FROM transactions t
                JOIN labels l USING (tx_id)
                WHERE l.is_laundering AND NOT t.is_self_transfer AND t.ts BETWEEN ? AND ?
                UNION ALL
                SELECT t.to_bank, t.to_account FROM transactions t JOIN labels l USING (tx_id)
                WHERE l.is_laundering AND NOT t.is_self_transfer AND t.ts BETWEEN ? AND ?))
        , pattern_pos AS (
            SELECT DISTINCT b, a FROM (
                SELECT t.from_bank AS b, t.from_account AS a FROM transactions t
                JOIN pattern_transactions pt USING (tx_id) WHERE t.ts BETWEEN ? AND ?
                UNION ALL
                SELECT t.to_bank, t.to_account FROM transactions t
                JOIN pattern_transactions pt USING (tx_id) WHERE t.ts BETWEEN ? AND ?))
        SELECT r.case_score, r.score, pos.b IS NOT NULL, pp.b IS NOT NULL
        FROM account_risk r
        LEFT JOIN pos USING (b, a)
        LEFT JOIN pattern_pos pp USING (b, a)
        ANTI JOIN excluded e ON e.b = r.b AND e.a = r.a
        """,
        [start, end, start, end, start, end, start, end],
    ).fetchall()
    case_table, case_ap, positives, total = threshold_table(
        [(r[0], r[2]) for r in rows], subgroup=[r[3] for r in rows]
    )
    _, subject_ap, _, _ = threshold_table([(r[1], r[2]) for r in rows])
    return {
        "period": name,
        "accounts": total,
        "positive_accounts": positives,
        "base_rate": round(positives / total, 5),
        "pattern_positive_accounts": sum(1 for r in rows if r[3]),
        "average_precision_case_score": case_ap,
        "average_precision_subject_score": subject_ap,
        "thresholds": case_table,
    }


def transaction_level(con, name: str, start: datetime, end: datetime) -> dict:
    score_population(con, start, end)
    rows = con.execute(
        """
        SELECT greatest(COALESCE(s.case_score, 0), COALESCE(r.case_score, 0)) AS score,
               l.is_laundering
        FROM transactions t
        JOIN labels l USING (tx_id)
        LEFT JOIN account_risk s ON s.b = t.from_bank AND s.a = t.from_account
        LEFT JOIN account_risk r ON r.b = t.to_bank AND r.a = t.to_account
        WHERE NOT t.is_self_transfer AND t.ts BETWEEN ? AND ?
          AND (t.from_bank, t.from_account) NOT IN (SELECT (b, a) FROM excluded)
          AND (t.to_bank, t.to_account) NOT IN (SELECT (b, a) FROM excluded)
        """,
        [start, end],
    ).fetchall()
    table, ap, positives, total = threshold_table([(r[0], r[1]) for r in rows])
    for row in table:
        p, rc = row["precision"], row["recall"]
        row["f1"] = round(2 * p * rc / (p + rc), 4) if p + rc else 0.0
    best = max(table, key=lambda r: r["f1"]) if table else None
    return {
        "period": name,
        "transactions": total,
        "laundering_transactions": positives,
        "base_rate": round(positives / total, 6),
        "average_precision": ap,
        "best_f1": best,
        "thresholds": table,
    }


def main() -> None:
    con = connect()
    excluded_accounts(con)
    n_excluded = con.execute("SELECT count(*) FROM excluded").fetchone()[0]
    result = {
        "created_utc": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "excluded_eval_accounts": n_excluded,
        "account_level": [account_level(con, *p) for p in ACCOUNT_PERIODS],
        "transaction_level": transaction_level(con, *TEST_PERIOD),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"detection-{result['created_utc']}.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    for p in result["account_level"]:
        print(
            f"\n{p['period']}: {p['accounts']:,} accounts, {p['positive_accounts']:,} positive "
            f"(base rate {p['base_rate']:.2%}); AP case score {p['average_precision_case_score']}, "
            f"subject only {p['average_precision_subject_score']}"
        )
        print("  threshold  alerts  true  recall  precision  alerts/true  recall(pattern)")
        for r in p["thresholds"]:
            if r["threshold"] >= 3:
                print(
                    f"  >= {r['threshold']:<6} {r['alerts']:>7,} {r['true_cases']:>5} "
                    f"{r['recall']:>7.2%} {r['precision']:>9.2%} {r['alerts_per_true_case']!s:>10}"
                    f"  {r['recall_pattern_laundering']:.2%}"
                )
    t = result["transaction_level"]
    b = t["best_f1"]
    print(
        f"\n{t['period']}: {t['transactions']:,} transactions, "
        f"{t['laundering_transactions']} laundering "
        f"(base rate {t['base_rate']:.3%}); AP {t['average_precision']}; best F1 {b['f1']:.2%} at "
        f"threshold {b['threshold']} (precision {b['precision']:.2%}, recall {b['recall']:.2%})"
    )
    print(f"written: {out}")


if __name__ == "__main__":
    main()
