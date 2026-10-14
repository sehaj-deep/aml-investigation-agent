"""Train the detection model once, score the test period, and write explained alerts.

    python -m pip install --require-hashes -r requirements-detection.txt
    python scripts/train_detection.py

Outputs:
- data/detection/model.json (gitignored): the trained model;
- evals/runs/detection/model-<stamp>.json: metrics against the rules, on the test period;
- evals/alerts/detection/alerts.jsonl: an alert queue for the investigation evaluation:
  a seeded random sample of the accounts above the alert threshold (the top 2,000 of
  the test period, about a quarter of them real laundering), with the factors behind
  each score. Sampling from the queue, not taking only the top, keeps a realistic mix
  of true and false alerts for measuring triage;
- evals/alerts/detection/ground_truth.jsonl: their labels, kept apart from the alerts.
Accounts of the frozen label-built evaluation set are excluded from training and
validation. No language model is used.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np

from aml_agent import config
from aml_agent.alerts.io import read_alerts, read_truth
from aml_agent.data.tooldb import tool_db_path
from aml_agent.detection import model as dm
from aml_agent.detection.features import FEATURES, build_currency_stats

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "evals" / "runs" / "detection"
ALERTS = ROOT / "evals" / "alerts" / "detection"
BUDGETS = (100, 250, 500, 1000, 2000)


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    con.execute(f"ATTACH '{tool_db_path().as_posix()}' AS src (READ_ONLY)")
    con.execute("CREATE VIEW transactions AS SELECT * FROM src.transactions")
    for table in ("pattern_transactions", "pattern_accounts", "other_laundering"):
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM '{config.table_path(table).as_posix()}'")
    con.execute(
        "CREATE VIEW labels AS SELECT tx_id, is_laundering FROM "
        f"'{config.table_path('transactions').as_posix()}'"
    )
    return con


def eval_set_accounts(con: duckdb.DuckDBPyConnection) -> set[tuple[int, str]]:
    blocks = sorted({t.block_id for t in read_truth("eval") if t.block_id})
    accounts = {(a.seed_bank, a.seed_account) for a in read_alerts("eval")}
    accounts |= set(
        con.execute(
            "SELECT DISTINCT bank_id, account FROM pattern_accounts "
            "WHERE block_id IN (SELECT unnest(?))",
            [blocks],
        ).fetchall()
    )
    return accounts


def transaction_f1(con, data: dm.Dataset, scores: np.ndarray, start: datetime, end: datetime):
    """Transaction-level precision, recall and F1 at every score cut.

    A transfer's score is the lower of its two accounts' scores: a laundering transfer
    links two involved accounts, so both ends must look risky.
    """
    con.register(
        "acct_scores",
        {
            "b": np.array([b for b, _ in data.accounts], dtype=np.int64),
            "a": np.array([a for _, a in data.accounts], dtype=object),
            "p": scores.astype(float),
        },
    )
    rows = con.execute(
        """
        SELECT least(COALESCE(s.p, 0), COALESCE(r.p, 0)) AS score, l.is_laundering
        FROM transactions t JOIN labels l USING (tx_id)
        LEFT JOIN acct_scores s ON s.b = t.from_bank AND s.a = t.from_account
        LEFT JOIN acct_scores r ON r.b = t.to_bank AND r.a = t.to_account
        WHERE NOT t.is_self_transfer AND t.ts BETWEEN ? AND ?
        """,
        [start, end],
    ).fetchall()
    con.unregister("acct_scores")
    s = np.array([r[0] for r in rows])
    y = np.array([1 if r[1] else 0 for r in rows])
    order = np.argsort(-s, kind="stable")
    tp = np.cumsum(y[order])
    k = np.arange(1, len(s) + 1)
    precision = tp / k
    recall = tp / max(y.sum(), 1)
    f1 = np.where(precision + recall > 0, 2 * precision * recall / (precision + recall), 0)
    return s[order], precision, recall, f1, int(y.sum()), len(s)


def at_threshold(sorted_scores, precision, recall, f1, threshold: float) -> dict:
    idx = int(np.searchsorted(-sorted_scores, -threshold, side="right")) - 1
    if idx < 0:
        return {"threshold": threshold, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    return {
        "threshold": round(float(threshold), 5),
        "flagged": idx + 1,
        "precision": round(float(precision[idx]), 4),
        "recall": round(float(recall[idx]), 4),
        "f1": round(float(f1[idx]), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=2000, help="alert threshold: top N accounts")
    parser.add_argument("--alerts", type=int, default=150, help="alerts sampled from the queue")
    parser.add_argument("--seed", type=int, default=20261014)
    args = parser.parse_args()
    started = time.perf_counter()
    con = connect()
    build_currency_stats(con)
    excluded = eval_set_accounts(con)

    train_sets = [dm.labeled_features(con, s, e, excluded) for s, e in dm.TRAIN_PERIODS]
    validation = dm.labeled_features(con, *dm.VALIDATION_PERIOD, excluded)
    test = dm.labeled_features(con, *dm.TEST_PERIOD)
    booster = dm.train(train_sets, validation)
    model_dir = config.parquet_dir().parent / "detection"
    model_dir.mkdir(parents=True, exist_ok=True)
    booster.save_model(model_dir / "model.json")

    val_scores = dm.predict(booster, validation)
    test_scores = dm.predict(booster, test)
    rule_index = (FEATURES.index("rule_score"), FEATURES.index("top_counterparty_score"))
    rules_case = test.x[:, rule_index[0]] + test.x[:, rule_index[1]]

    # Pattern laundering in the test period (a subgroup of positives).
    pattern = set(
        con.execute(
            """
            SELECT DISTINCT b, a FROM (
                SELECT t.from_bank AS b, t.from_account AS a FROM transactions t
                JOIN pattern_transactions USING (tx_id) WHERE t.ts BETWEEN ? AND ?
                UNION ALL
                SELECT t.to_bank, t.to_account FROM transactions t
                JOIN pattern_transactions USING (tx_id) WHERE t.ts BETWEEN ? AND ?)
            """,
            [*dm.TEST_PERIOD, *dm.TEST_PERIOD],
        ).fetchall()
    )
    is_pattern = np.array([1 if acc in pattern else 0 for acc in test.accounts])

    budgets = []
    for name, scores in (("model", test_scores), ("rules", rules_case)):
        order = np.argsort(-scores, kind="stable")
        for k in BUDGETS:
            top = order[:k]
            budgets.append(
                {
                    "scorer": name,
                    "alerts": k,
                    "true_cases": int(test.y[top].sum()),
                    "precision": round(float(test.y[top].mean()), 4),
                    "recall": round(float(test.y[top].sum() / test.y.sum()), 4),
                    "recall_pattern": round(
                        float(is_pattern[top].sum() / max(is_pattern.sum(), 1)), 4
                    ),
                }
            )

    # Transaction-level F1: threshold chosen on validation, applied once to test.
    v = transaction_f1(con, validation, val_scores, *dm.VALIDATION_PERIOD)
    best_val = int(np.argmax(v[3]))
    chosen = float(v[0][best_val])
    t = transaction_f1(con, test, test_scores, *dm.TEST_PERIOD)
    tx_test = at_threshold(t[0], t[1], t[2], t[3], chosen)
    tx_oracle = int(np.argmax(t[3]))

    gain = booster.get_score(importance_type="gain")
    importance = sorted(gain.items(), key=lambda kv: -kv[1])[:12]

    # Alert queue: accounts above the threshold (top `budget`); a seeded sample of it
    # becomes the investigation alert set, ordered by score.
    queue = np.argsort(-test_scores, kind="stable")[: args.budget]
    rng = np.random.default_rng(args.seed)
    order = sorted(
        rng.choice(queue, size=args.alerts, replace=False), key=lambda i: -test_scores[i]
    )
    rank_of = {int(i): r for r, i in enumerate(queue, start=1)}
    factors = dm.top_factors(booster, test, list(order))
    ALERTS.mkdir(parents=True, exist_ok=True)
    start, end = dm.TEST_PERIOD
    alert_lines, truth_lines = [], []
    for rank, (i, f) in enumerate(zip(order, factors, strict=True), start=1):
        bank, acct = test.accounts[i]
        alert_id = f"det-{rank:04d}"
        queue_rank = rank_of[int(i)]
        alert_lines.append(
            {
                "alert_id": alert_id,
                "seed_bank": bank,
                "seed_account": acct,
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "detection_score": round(float(test_scores[i]), 5),
                "detection_rank": queue_rank,
                "detection_factors": f,
            }
        )
        blocks = [
            r[0]
            for r in con.execute(
                """
                SELECT DISTINCT pt.block_id FROM pattern_transactions pt
                JOIN transactions t USING (tx_id)
                WHERE t.ts BETWEEN ? AND ? AND ((t.from_bank = ? AND t.from_account = ?)
                   OR (t.to_bank = ? AND t.to_account = ?))
                ORDER BY 1
                """,
                [start, end, bank, acct, bank, acct],
            ).fetchall()
        ]
        truth_lines.append(
            {
                "alert_id": alert_id,
                "label": "positive" if test.y[i] else "benign",
                "pattern_blocks": blocks,
                "other_laundering_only": bool(test.y[i]) and not blocks,
            }
        )
    (ALERTS / "alerts.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in alert_lines), encoding="utf-8"
    )
    (ALERTS / "ground_truth.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in truth_lines), encoding="utf-8"
    )

    result = {
        "created_utc": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "model": "XGBoost on account features (aml_agent/detection)",
        "params": dm.PARAMS,
        "best_iteration": booster.best_iteration,
        "features": list(FEATURES),
        "periods": {
            "train": [[s.isoformat(), e.isoformat()] for s, e in dm.TRAIN_PERIODS],
            "validation": [p.isoformat() for p in dm.VALIDATION_PERIOD],
            "test": [p.isoformat() for p in dm.TEST_PERIOD],
        },
        "rows": {
            "train": int(sum(len(d.y) for d in train_sets)),
            "train_positive": int(sum(d.y.sum() for d in train_sets)),
            "test": len(test.y),
            "test_positive": int(test.y.sum()),
            "test_pattern_positive": int(is_pattern.sum()),
        },
        "account_level_test": {
            "base_rate": round(float(test.y.mean()), 5),
            "average_precision_model": round(dm.average_precision(test_scores, test.y), 4),
            "average_precision_rules": round(dm.average_precision(rules_case, test.y), 4),
            "validation_average_precision_model": round(
                dm.average_precision(val_scores, validation.y), 4
            ),
            "alert_budgets": budgets,
        },
        "transaction_level_test": {
            "laundering_transactions": t[4],
            "transactions": t[5],
            "threshold_from_validation": tx_test,
            "best_on_test_optimistic": {
                "precision": round(float(t[1][tx_oracle]), 4),
                "recall": round(float(t[2][tx_oracle]), 4),
                "f1": round(float(t[3][tx_oracle]), 4),
            },
        },
        "top_features_by_gain": [[k, round(v, 2)] for k, v in importance],
        "alert_queue": {"budget": args.budget, "sample": args.alerts, "seed": args.seed},
        "alerts_written": len(alert_lines),
        "alerts_true": int(sum(1 for x in truth_lines if x["label"] == "positive")),
        "seconds": round(time.perf_counter() - started, 1),
    }
    RUNS.mkdir(parents=True, exist_ok=True)
    out = RUNS / f"model-{result['created_utc']}.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: result[k] for k in ("rows", "account_level_test", "transaction_level_test")},
            indent=1,
        )
    )
    print("alerts:", result["alerts_written"], "true:", result["alerts_true"])
    print("top features:", result["top_features_by_gain"][:8])
    print(f"done in {result['seconds']} s; written {out}")


if __name__ == "__main__":
    main()
