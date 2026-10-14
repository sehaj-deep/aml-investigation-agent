"""Train, evaluate and explain the detection model (XGBoost on account features).

Split, following the dataset authors' chronological 60/20/20 advice on the primary
period: training periods before 2022-09-06 13:36, validation up to 2022-09-08 16:12,
test after it to the end of Sep 10. The unit is an account in a review period; it is
positive if it sends or receives any labeled laundering transaction in that period.
Labels are read from the Parquet source only to build training targets and to score
the test period; the features never see them.

The validation period is used only for early stopping and to choose the transaction
F1 threshold. The test period is scored once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import duckdb
import numpy as np
import xgboost as xgb

from aml_agent.detection.features import FEATURES, build_features

TRAIN_PERIODS = [
    (datetime(2022, 9, 2), datetime(2022, 9, 3, 23, 59)),
    (datetime(2022, 9, 4), datetime(2022, 9, 6, 13, 35)),
]
VALIDATION_PERIOD = (datetime(2022, 9, 6, 13, 36), datetime(2022, 9, 8, 16, 11))
TEST_PERIOD = (datetime(2022, 9, 8, 16, 12), datetime(2022, 9, 10, 23, 59))

PARAMS = {
    "objective": "binary:logistic",
    "eval_metric": "aucpr",
    "tree_method": "hist",
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "seed": 7,
    "nthread": 8,
}
MAX_ROUNDS = 2000
EARLY_STOPPING = 100

FEATURE_LABELS = {
    "n_transfers": "number of transfers",
    "n_in": "incoming transfers",
    "n_out": "outgoing transfers",
    "n_cp": "number of counterparties",
    "receives_and_pays": "both receives and pays",
    "currency_switch": "currency conversion pass-through",
    "new_counterparty_share": "share of new counterparties",
    "one_time_counterparty_share": "share of one-time relationships",
    "period_activity_share": "activity concentrated in the period",
    "onward_within_24h_share": "rapid onward transfers",
    "rule_score": "red-flag rule score",
    "top_counterparty_score": "riskiest first-time counterparty",
    "senders": "distinct senders",
    "receivers": "distinct receivers",
    "one_off_senders": "one-time senders",
    "one_off_receivers": "one-time receivers",
    "reciprocal_counterparties": "two-way counterparties",
    "currencies_in": "currencies received",
    "currencies_out": "currencies paid",
    "amount_z_mean": "typical amount size for its currency",
    "amount_z_max": "largest amount for its currency",
    "amount_z_min": "smallest amount for its currency",
    "amount_z_std": "spread of amounts",
    "active_hours_span": "hours between first and last transfer",
    "transfers_per_active_day": "transfers per active day",
    "median_hours_to_onward": "time from receiving to paying on",
    "cp_rule_score_mean": "counterparties' average red-flag score",
    "cp_rule_score_max": "counterparties' highest red-flag score",
    "cp_currency_switch_count": "counterparties converting currency",
    "cp_degree_max": "largest counterparty network",
    "cp_one_time_share_mean": "counterparties' one-time relationships",
}


@dataclass
class Dataset:
    accounts: list[tuple[int, str]]
    x: np.ndarray
    y: np.ndarray


def labeled_features(
    con: duckdb.DuckDBPyConnection,
    start: datetime,
    end: datetime,
    exclude: set[tuple[int, str]] | None = None,
) -> Dataset:
    """Features and labels for every account active in [start, end]."""
    build_features(con, start, end)
    cols = ", ".join(f"f.{c}" for c in FEATURES)
    rows = con.execute(
        f"""
        WITH pos AS (
            SELECT DISTINCT b, a FROM (
                SELECT t.from_bank AS b, t.from_account AS a FROM transactions t
                JOIN labels l USING (tx_id)
                WHERE l.is_laundering AND NOT t.is_self_transfer AND t.ts BETWEEN ? AND ?
                UNION ALL
                SELECT t.to_bank, t.to_account FROM transactions t JOIN labels l USING (tx_id)
                WHERE l.is_laundering AND NOT t.is_self_transfer AND t.ts BETWEEN ? AND ?))
        SELECT f.b, f.a, pos.b IS NOT NULL, {cols}
        FROM features f LEFT JOIN pos USING (b, a)
        ORDER BY f.b, f.a
        """,
        [start, end, start, end],
    ).fetchall()
    if exclude:
        rows = [r for r in rows if (r[0], r[1]) not in exclude]
    x = np.array([[np.nan if v is None else float(v) for v in r[3:]] for r in rows], dtype=float)
    y = np.array([1 if r[2] else 0 for r in rows], dtype=int)
    return Dataset([(r[0], r[1]) for r in rows], x, y)


def average_precision(scores: np.ndarray, y: np.ndarray) -> float:
    order = np.argsort(-scores, kind="stable")
    hits = y[order]
    tp = np.cumsum(hits)
    precision = tp / np.arange(1, len(hits) + 1)
    return float((precision * hits).sum() / max(hits.sum(), 1))


def train(train_sets: list[Dataset], validation: Dataset) -> xgb.Booster:
    x = np.vstack([d.x for d in train_sets])
    y = np.concatenate([d.y for d in train_sets])
    params = {**PARAMS, "scale_pos_weight": float(np.sqrt((y == 0).sum() / max((y == 1).sum(), 1)))}
    dtrain = xgb.DMatrix(x, label=y, feature_names=list(FEATURES))
    dval = xgb.DMatrix(validation.x, label=validation.y, feature_names=list(FEATURES))
    return xgb.train(
        params,
        dtrain,
        num_boost_round=MAX_ROUNDS,
        evals=[(dval, "validation")],
        early_stopping_rounds=EARLY_STOPPING,
        verbose_eval=False,
    )


def predict(model: xgb.Booster, data: Dataset) -> np.ndarray:
    dm = xgb.DMatrix(data.x, feature_names=list(FEATURES))
    return model.predict(dm, iteration_range=(0, model.best_iteration + 1))


def top_factors(model: xgb.Booster, data: Dataset, rows: list[int], k: int = 3) -> list[list[dict]]:
    """The k features pushing each selected row's score up the most (SHAP contributions)."""
    dm = xgb.DMatrix(data.x[rows], feature_names=list(FEATURES))
    contribs = model.predict(dm, pred_contribs=True, iteration_range=(0, model.best_iteration + 1))
    out = []
    for i, row in enumerate(contribs):
        feats = row[:-1]  # last column is the bias
        best = np.argsort(-feats)[:k]
        out.append(
            [
                {
                    "feature": FEATURES[j],
                    "label": FEATURE_LABELS[FEATURES[j]],
                    "value": None
                    if np.isnan(data.x[rows[i], j])
                    else round(float(data.x[rows[i], j]), 4),
                    "contribution": round(float(feats[j]), 4),
                }
                for j in best
                if feats[j] > 0
            ]
        )
    return out
