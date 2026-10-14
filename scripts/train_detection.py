"""Train the transaction monitoring model, score the test period, and write alerts.

    python -m pip install --require-hashes -r requirements-detection.txt
    python scripts/train_detection.py

Two models are trained on IBM's 60/20/20 time split: one with payment format (the
product model, since analysts see it) and one without (payment format is unusually
predictive in this simulator). Both are compared with the red-flag rules.

Outputs:
- data/detection/model.json and model-no-format.json (gitignored);
- evals/runs/detection/model-<stamp>.json: test-period metrics;
- evals/alerts/detection/alerts.jsonl: an alert queue for the investigation
  evaluation. An account is alerted when any of its test-period transactions scores
  above the threshold chosen on validation; a seeded sample of those accounts is
  written, each with its triggering transactions and the factors behind the top one;
- evals/alerts/detection/ground_truth.jsonl: their labels, kept apart from the alerts.
Accounts of the frozen label-built evaluation set are excluded from training and
validation. No language model is used.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np

from aml_agent import config
from aml_agent.alerts.io import read_alerts, read_truth
from aml_agent.data.tooldb import tool_db_path
from aml_agent.detection import model as dm
from aml_agent.detection.features import build_currency_stats
from aml_agent.detection.transactions import build_history

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "evals" / "runs" / "detection"
ALERTS = ROOT / "evals" / "alerts" / "detection"
BUDGETS = (100, 250, 500, 1000, 2000)
MAX_TRIGGERS = 25
WINDOW_PAD = timedelta(hours=24)


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


def concat(parts: list[dm.Dataset]) -> dm.Dataset:
    return dm.Dataset(
        tx_id=np.concatenate([p.tx_id for p in parts]),
        ts=np.concatenate([p.ts for p in parts]),
        sender=[a for p in parts for a in p.sender],
        receiver=[a for p in parts for a in p.receiver],
        x=np.vstack([p.x for p in parts]),
        y=np.concatenate([p.y for p in parts]),
    )


def rules_score(data: dm.Dataset) -> np.ndarray:
    """The rules' transaction score: the lower case score of its two accounts."""
    i = dm.ALL_FEATURES.index

    def case(prefix: str) -> np.ndarray:
        s = data.x[:, i(f"{prefix}rule_score")] + data.x[:, i(f"{prefix}top_counterparty_score")]
        return np.nan_to_num(s, nan=0.0)

    return np.minimum(case("s_"), case("r_"))


def evaluate(name, val_scores, validation, test_scores, test) -> dict:
    """Threshold from validation, applied once to test; plus the optimistic best."""
    threshold = dm.best_threshold(val_scores, validation.y)
    primary = test.ts <= np.datetime64(dm.PRIMARY_END)
    _, precision, recall, f1 = dm.f1_curve(test_scores, test.y)
    best = int(np.argmax(f1))
    return {
        "scorer": name,
        "average_precision": round(dm.average_precision(test_scores, test.y), 4),
        "validation_average_precision": round(dm.average_precision(val_scores, validation.y), 4),
        "threshold_from_validation": dm.at_threshold(test_scores, test.y, threshold),
        "best_on_test_optimistic": {
            "precision": round(float(precision[best]), 4),
            "recall": round(float(recall[best]), 4),
            "f1": round(float(f1[best]), 4),
        },
        "without_rows_after_sep_10": dm.at_threshold(
            test_scores[primary], test.y[primary], threshold
        ),
    }


def account_scores(con, test: dm.Dataset, scores: np.ndarray):
    """Each test-period account's highest transaction score, and whether it laundered."""
    con.register(
        "scored",
        {
            "sb": np.array([b for b, _ in test.sender], dtype=np.int64),
            "sa": np.array([a for _, a in test.sender], dtype=object),
            "rb": np.array([b for b, _ in test.receiver], dtype=np.int64),
            "ra": np.array([a for _, a in test.receiver], dtype=object),
            "p": scores.astype(float),
            "y": test.y.astype(np.int64),
        },
    )
    rows = con.execute(
        """
        SELECT b, a, max(p) AS p, max(y) AS y FROM (
            SELECT sb AS b, sa AS a, p, y FROM scored
            UNION ALL
            SELECT rb, ra, p, y FROM scored WHERE NOT (rb = sb AND ra = sa))
        GROUP BY ALL ORDER BY b, a
        """
    ).fetchall()
    con.unregister("scored")
    accounts = [(r[0], r[1]) for r in rows]
    return accounts, np.array([r[2] for r in rows]), np.array([r[3] for r in rows], dtype=int)


def budgets(scores: np.ndarray, y: np.ndarray, name: str) -> list[dict]:
    order = np.argsort(-scores, kind="stable")
    return [
        {
            "scorer": name,
            "alerts": k,
            "true_cases": int(y[order[:k]].sum()),
            "precision": round(float(y[order[:k]].mean()), 4),
            "recall": round(float(y[order[:k]].sum() / y.sum()), 4),
        }
        for k in BUDGETS
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alerts", type=int, default=150, help="alerts sampled from the queue")
    parser.add_argument("--seed", type=int, default=20261014)
    args = parser.parse_args()
    started = time.perf_counter()
    con = connect()
    build_currency_stats(con, dm.TRAIN_PERIODS[0][0], dm.TRAIN_PERIODS[-1][1])
    build_history(con)
    excluded = eval_set_accounts(con)

    train_set = concat(
        [
            dm.labeled_transactions(con, s, e, excluded, sample_negatives=dm.NEGATIVE_SAMPLE)
            for s, e in dm.TRAIN_PERIODS
        ]
    )
    validation = dm.labeled_transactions(con, *dm.VALIDATION_PERIOD, excluded)
    test = dm.labeled_transactions(con, *dm.TEST_PERIOD)
    print(f"features built in {time.perf_counter() - started:.0f} s", flush=True)

    model_dir = config.parquet_dir().parent / "detection"
    model_dir.mkdir(parents=True, exist_ok=True)
    models, results = {}, []
    for name, with_format in (("model", True), ("model_without_format", False)):
        booster = dm.train(train_set, validation, with_format)
        booster.save_model(model_dir / ("model.json" if with_format else "model-no-format.json"))
        val_scores, test_scores = dm.predict(booster, validation), dm.predict(booster, test)
        models[name] = (booster, val_scores, test_scores)
        results.append(
            {
                **evaluate(name, val_scores, validation, test_scores, test),
                "best_iteration": booster.best_iteration,
            }
        )
        print(name, results[-1]["threshold_from_validation"], flush=True)
    results.append(evaluate("rules", rules_score(validation), validation, rules_score(test), test))

    booster, val_scores, test_scores = models["model"]
    threshold = dm.best_threshold(val_scores, validation.y)
    accounts, acc_scores, acc_y = account_scores(con, test, test_scores)
    rules_accounts, rules_acc, _ = account_scores(con, test, rules_score(test))
    assert rules_accounts == accounts
    gain = booster.get_score(importance_type="gain")
    importance = sorted(gain.items(), key=lambda kv: -kv[1])[:15]

    # Alert queue: every account with a transaction above the threshold.
    flagged = test_scores >= threshold
    queue = [int(i) for i in np.argsort(-acc_scores, kind="stable") if acc_scores[i] >= threshold]
    rng = np.random.default_rng(args.seed)
    sample = sorted(
        (int(i) for i in rng.choice(queue, size=min(args.alerts, len(queue)), replace=False)),
        key=lambda i: -acc_scores[i],
    )
    rank_of = {i: r for r, i in enumerate(queue, start=1)}
    tx_rows: dict[tuple[int, str], list[int]] = {}
    for j in np.flatnonzero(flagged):
        tx_rows.setdefault(test.sender[j], []).append(int(j))
        if test.receiver[j] != test.sender[j]:
            tx_rows.setdefault(test.receiver[j], []).append(int(j))
    triggers = {
        i: sorted(tx_rows[accounts[i]], key=lambda j: -test_scores[j])[:MAX_TRIGGERS]
        for i in sample
    }
    factors = dm.top_factors(booster, test, [triggers[i][0] for i in sample])

    alert_lines, truth_lines = [], []
    period_start, period_end = dm.TEST_PERIOD
    for n, (i, f) in enumerate(zip(sample, factors, strict=True), start=1):
        bank, acct = accounts[i]
        rows = triggers[i]
        times = [test.ts[j].astype("datetime64[m]").astype(datetime) for j in rows]
        alert_id = f"det-{n:04d}"
        alert_lines.append(
            {
                "alert_id": alert_id,
                "seed_bank": bank,
                "seed_account": acct,
                "window_start": max(min(times) - WINDOW_PAD, period_start).isoformat(),
                "window_end": min(max(times) + WINDOW_PAD, period_end).isoformat(),
                "detection_score": round(float(acc_scores[i]), 5),
                "detection_rank": rank_of[i],
                "trigger_tx_ids": [int(test.tx_id[j]) for j in rows],
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
                [period_start, period_end, bank, acct, bank, acct],
            ).fetchall()
        ]
        truth_lines.append(
            {
                "alert_id": alert_id,
                "label": "positive" if acc_y[i] else "benign",
                "true_triggers": int(sum(test.y[j] for j in rows)),
                "pattern_blocks": blocks,
                "other_laundering_only": bool(acc_y[i]) and not blocks,
            }
        )
    ALERTS.mkdir(parents=True, exist_ok=True)
    for name, lines in (("alerts.jsonl", alert_lines), ("ground_truth.jsonl", truth_lines)):
        (ALERTS / name).write_text(
            "".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8", newline="\n"
        )

    after = test.ts > np.datetime64(dm.PRIMARY_END)
    result = {
        "created_utc": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "model": "XGBoost transaction monitoring (aml_agent/detection)",
        "split": "IBM AMLworld 60/20/20 by time",
        "params": dm.PARAMS,
        "negative_sample_in_training": dm.NEGATIVE_SAMPLE,
        "features": list(dm.ALL_FEATURES),
        "periods": {
            "train": [[s.isoformat(), e.isoformat()] for s, e in dm.TRAIN_PERIODS],
            "validation": [p.isoformat() for p in dm.VALIDATION_PERIOD],
            "test": [p.isoformat() for p in dm.TEST_PERIOD],
        },
        "rows": {
            "train_sampled": len(train_set),
            "train_laundering": int(train_set.y.sum()),
            "validation": len(validation),
            "validation_laundering": int(validation.y.sum()),
            "test": len(test),
            "test_laundering": int(test.y.sum()),
            "test_after_sep_10": int(after.sum()),
            "test_laundering_after_sep_10": int(test.y[after].sum()),
        },
        "transaction_level_test": results,
        "account_level_test": {
            "accounts": len(accounts),
            "laundering_accounts": int(acc_y.sum()),
            "alerted_at_threshold": len(queue),
            "alerted_laundering": int(sum(acc_y[i] for i in queue)),
            "alert_budgets": budgets(acc_scores, acc_y, "model")
            + budgets(rules_acc, acc_y, "rules"),
        },
        "top_features_by_gain": [[k, round(v, 2)] for k, v in importance],
        "alert_queue": {"sample": len(sample), "seed": args.seed},
        "alerts_true": int(sum(1 for x in truth_lines if x["label"] == "positive")),
        "seconds": round(time.perf_counter() - started, 1),
    }
    RUNS.mkdir(parents=True, exist_ok=True)
    out = RUNS / f"model-{result['created_utc']}.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: result[k] for k in ("rows", "transaction_level_test")}, indent=1))
    print(json.dumps(result["account_level_test"], indent=1))
    print("alerts:", len(alert_lines), "true:", result["alerts_true"])
    print("top features:", result["top_features_by_gain"][:10])
    print(f"done in {result['seconds']} s; written {out}")


if __name__ == "__main__":
    main()
