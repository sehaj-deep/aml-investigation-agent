"""Train, evaluate and explain the transaction monitoring model (XGBoost).

Split: IBM's AMLworld benchmark split, 60/20/20 of all transactions in time order
(the cutoffs are golden numbers: 2022-09-06 13:36 and 2022-09-08 16:12). Training
covers Sep 1 to the first cutoff, validation to the second, test to the end of the
data (Sep 18), including the rows after Sep 10. Validation is used only for early
stopping and to choose the alert threshold; the test period is scored once.

Account features are computed per review period, so the training part is cut into
two periods of about the same length as validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import duckdb
import numpy as np
import xgboost as xgb

from aml_agent.detection.features import FEATURES
from aml_agent.detection.transactions import (
    FORMAT_FEATURES,
    TX_FEATURES,
    build_transaction_features,
    feature_names,
)

TRAIN_PERIODS = [
    (datetime(2022, 9, 1), datetime(2022, 9, 3, 23, 59)),
    (datetime(2022, 9, 4), datetime(2022, 9, 6, 13, 35)),
]
VALIDATION_PERIOD = (datetime(2022, 9, 6, 13, 36), datetime(2022, 9, 8, 16, 11))
TEST_PERIOD = (datetime(2022, 9, 8, 16, 12), datetime(2022, 9, 18, 23, 59))
PRIMARY_END = datetime(2022, 9, 10, 23, 59)

# Training keeps every laundering transaction and one in NEGATIVE_SAMPLE others.
NEGATIVE_SAMPLE = 5

PARAMS = {
    "objective": "binary:logistic",
    "eval_metric": "aucpr",
    "tree_method": "hist",
    "max_depth": 7,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "seed": 7,
    "nthread": 8,
}
MAX_ROUNDS = 3000
EARLY_STOPPING = 150

ACCOUNT_LABELS = {
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
TX_LABELS = {
    "amount_z": "payment size for its currency",
    "cross_currency": "paid and received in different currencies",
    "same_bank": "both accounts at the same bank",
    "self_transfer": "transfer between the same account",
    "hour": "hour of the payment",
    "pair_prior_count": "earlier payments between the two accounts",
    "pair_reverse_prior_count": "earlier payments in the other direction",
    "pair_period_count": "payments between the two accounts in the period",
    "hours_since_sender_received": "time since the sender last received funds",
    "hours_to_receiver_pays": "time until the receiver pays on",
    "format_ach": "payment by ACH",
    "format_bitcoin": "payment in Bitcoin",
    "format_cash": "cash payment",
    "format_cheque": "payment by cheque",
    "format_credit_card": "credit card payment",
    "format_reinvestment": "reinvestment",
    "format_wire": "wire transfer",
    "sender_format_share": "how usual this payment type is for the sender",
    "receiver_format_share": "how usual this payment type is for the receiver",
}
FEATURE_LABELS = {
    **TX_LABELS,
    **{f"s_{k}": f"sender: {v}" for k, v in ACCOUNT_LABELS.items()},
    **{f"r_{k}": f"receiver: {v}" for k, v in ACCOUNT_LABELS.items()},
}


@dataclass
class Dataset:
    tx_id: np.ndarray
    ts: np.ndarray
    sender: list[tuple[int, str]]
    receiver: list[tuple[int, str]]
    x: np.ndarray  # every feature, with format columns; select with columns()
    y: np.ndarray

    def __len__(self) -> int:
        return len(self.y)


ALL_FEATURES = feature_names(with_format=True)


def columns(with_format: bool) -> list[int]:
    keep = set(feature_names(with_format))
    return [i for i, f in enumerate(ALL_FEATURES) if f in keep]


def labeled_transactions(
    con: duckdb.DuckDBPyConnection,
    start: datetime,
    end: datetime,
    exclude: set[tuple[int, str]] | None = None,
    sample_negatives: int = 1,
) -> Dataset:
    """Features and labels of every transaction in [start, end].

    `exclude` drops transactions touching those accounts; `sample_negatives` keeps one
    in N non-laundering transactions (seeded by tx_id).
    """
    build_transaction_features(con, start, end)
    con.execute("CREATE OR REPLACE TEMP TABLE excluded (b INTEGER, a VARCHAR)")
    if exclude:
        con.executemany("INSERT INTO excluded VALUES (?, ?)", sorted(exclude))
    cols = ", ".join(f"COALESCE(CAST(f.{c} AS DOUBLE), 'NaN'::DOUBLE) AS {c}" for c in ALL_FEATURES)
    data = con.execute(
        f"""
        SELECT f.tx_id, f.ts, f.from_bank, f.from_account, f.to_bank, f.to_account,
               l.is_laundering::INTEGER AS y, {cols}
        FROM tx_features f JOIN labels l USING (tx_id)
        WHERE NOT EXISTS (SELECT 1 FROM excluded e
                          WHERE (e.b = f.from_bank AND e.a = f.from_account)
                             OR (e.b = f.to_bank AND e.a = f.to_account))
          AND (l.is_laundering OR hash(f.tx_id) % {sample_negatives} = 0)
        ORDER BY f.tx_id
        """
    ).fetchnumpy()
    x = np.column_stack([np.asarray(data[c], dtype=np.float32) for c in ALL_FEATURES])
    return Dataset(
        tx_id=np.asarray(data["tx_id"]),
        ts=np.asarray(data["ts"]),
        sender=list(zip(data["from_bank"].tolist(), data["from_account"].tolist(), strict=True)),
        receiver=list(zip(data["to_bank"].tolist(), data["to_account"].tolist(), strict=True)),
        x=x,
        y=np.asarray(data["y"], dtype=int),
    )


def average_precision(scores: np.ndarray, y: np.ndarray) -> float:
    order = np.argsort(-scores, kind="stable")
    hits = y[order]
    tp = np.cumsum(hits)
    precision = tp / np.arange(1, len(hits) + 1)
    return float((precision * hits).sum() / max(hits.sum(), 1))


def f1_curve(scores: np.ndarray, y: np.ndarray):
    """Scores sorted high to low, with precision, recall and F1 at each cut."""
    order = np.argsort(-scores, kind="stable")
    tp = np.cumsum(y[order])
    precision = tp / np.arange(1, len(y) + 1)
    recall = tp / max(y.sum(), 1)
    denom = precision + recall
    f1 = np.divide(2 * precision * recall, denom, out=np.zeros_like(denom), where=denom > 0)
    return scores[order], precision, recall, f1


def at_threshold(scores: np.ndarray, y: np.ndarray, threshold: float) -> dict:
    flagged = scores >= threshold
    tp = int((flagged & (y == 1)).sum())
    precision = tp / max(int(flagged.sum()), 1)
    recall = tp / max(int(y.sum()), 1)
    f1 = 2 * precision * recall / (precision + recall) if tp else 0.0
    return {
        "threshold": round(float(threshold), 5),
        "flagged": int(flagged.sum()),
        "true_flagged": tp,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def best_threshold(scores: np.ndarray, y: np.ndarray) -> float:
    sorted_scores, _, _, f1 = f1_curve(scores, y)
    return float(sorted_scores[int(np.argmax(f1))])


def train(train_set: Dataset, validation: Dataset, with_format: bool) -> xgb.Booster:
    cols = columns(with_format)
    names = [ALL_FEATURES[i] for i in cols]
    y = train_set.y
    params = {**PARAMS, "scale_pos_weight": float(np.sqrt((y == 0).sum() / max((y == 1).sum(), 1)))}
    dtrain = xgb.DMatrix(train_set.x[:, cols], label=y, feature_names=names)
    dval = xgb.DMatrix(validation.x[:, cols], label=validation.y, feature_names=names)
    return xgb.train(
        params,
        dtrain,
        num_boost_round=MAX_ROUNDS,
        evals=[(dval, "validation")],
        early_stopping_rounds=EARLY_STOPPING,
        verbose_eval=False,
    )


def predict(model: xgb.Booster, data: Dataset) -> np.ndarray:
    cols = [ALL_FEATURES.index(f) for f in model.feature_names]
    dm = xgb.DMatrix(data.x[:, cols], feature_names=model.feature_names)
    return model.predict(dm, iteration_range=(0, model.best_iteration + 1))


def top_factors(model: xgb.Booster, data: Dataset, rows: list[int], k: int = 3) -> list[list[dict]]:
    """The k features pushing each selected transaction's score up the most (SHAP)."""
    cols = [ALL_FEATURES.index(f) for f in model.feature_names]
    x = data.x[rows][:, cols]
    dm = xgb.DMatrix(x, feature_names=model.feature_names)
    contribs = model.predict(dm, pred_contribs=True, iteration_range=(0, model.best_iteration + 1))
    out = []
    for i, row in enumerate(contribs):
        feats = row[:-1]  # last column is the bias
        best = np.argsort(-feats)[:k]
        out.append(
            [
                {
                    "feature": model.feature_names[j],
                    "label": FEATURE_LABELS[model.feature_names[j]],
                    "value": None if np.isnan(x[i, j]) else round(float(x[i, j]), 4),
                    "contribution": round(float(feats[j]), 4),
                }
                for j in best
                if feats[j] > 0
            ]
        )
    return out


__all__ = [
    "FEATURES",
    "FORMAT_FEATURES",
    "TX_FEATURES",
    "Dataset",
]
