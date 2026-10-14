"""Detection features on the synthetic tool database, and the model's split and metrics.

The model tests need the optional detection dependencies (requirements-detection.txt)
and are skipped without them.
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import pytest

from aml_agent.detection.features import FEATURES, build_currency_stats
from aml_agent.detection.transactions import (
    FORMAT_FEATURES,
    build_history,
    build_transaction_features,
    feature_names,
)
from tests import synthetic

START, END = datetime(2022, 9, 2), datetime(2022, 9, 3, 23, 59)


@pytest.fixture()
def con(tmp_path):
    path = synthetic.build(tmp_path)
    c = duckdb.connect()
    c.execute(f"ATTACH '{path.as_posix()}' AS src (READ_ONLY)")
    c.execute("CREATE VIEW transactions AS SELECT * FROM src.transactions")
    build_currency_stats(c, START, END)
    build_history(c)
    build_transaction_features(c, START, END)
    yield c
    c.close()


def account(con, name: str) -> dict:
    cols = ", ".join(FEATURES)
    values = con.execute(f"SELECT {cols} FROM features WHERE a = ?", [name]).fetchone()
    return dict(zip(FEATURES, values, strict=True))


def tx(con, tx_id: int) -> dict:
    cur = con.execute("SELECT * FROM tx_features WHERE tx_id = ?", [tx_id])
    return dict(zip([d[0] for d in cur.description], cur.fetchone(), strict=True))


def test_account_features_are_columns_without_labels(con):
    cols = [r[0] for r in con.execute("DESCRIBE features").fetchall()]
    assert cols == ["b", "a", *FEATURES]
    assert not {"is_laundering", "payment_format"} & set(cols)


def test_account_features_ignore_self_transfers(con):
    n, distinct = con.execute("SELECT count(*), count(DISTINCT (b, a)) FROM features").fetchone()
    assert n == distinct
    seed = account(con, "SEED0001")
    # 7 payments out and HOP00001's payment in; the two self-transfers are ignored.
    assert (seed["n_out"], seed["n_in"]) == (7, 1)
    assert seed["receivers"] == 6
    assert seed["currencies_out"] == 2


def test_every_transaction_in_the_period_is_scored(con):
    cols = {r[0] for r in con.execute("DESCRIBE tx_features").fetchall()}
    assert set(feature_names(with_format=True)) <= cols
    assert "is_laundering" not in cols
    ids = [r[0] for r in con.execute("SELECT tx_id FROM tx_features ORDER BY 1").fetchall()]
    assert ids == list(range(1, 12))  # self-transfers included; Sep 4 and later excluded


def test_transaction_history_and_timing(con):
    # tx 7: SEED0001 pays FAN00001 again (tx 1 was the first payment).
    assert tx(con, 7)["pair_prior_count"] == 1
    assert tx(con, 1)["pair_prior_count"] == 0
    # tx 8: FAN00001 pays HOP00001 one hour after receiving (tx 7) ...
    t8 = tx(con, 8)
    assert t8["hours_since_sender_received"] == 1.0
    # ... and HOP00001 pays on at midnight, 16 hours later (tx 11).
    assert t8["hours_to_receiver_pays"] == 16.0
    # tx 11: HOP00001 pays SEED0001; SEED0001 never paid HOP00001 before.
    assert tx(con, 11)["pair_reverse_prior_count"] == 0
    assert tx(con, 9)["self_transfer"] == 1
    assert tx(con, 7)["cross_currency"] == 0


def test_payment_format_is_seen_only_by_the_format_model(con):
    t1 = tx(con, 1)
    assert t1["format_wire"] == 1 and t1["format_ach"] == 0
    assert t1["sender_format_share"] == 1.0
    assert not set(FORMAT_FEATURES) & set(feature_names(with_format=False))


def test_split_is_ordered_and_disjoint():
    dm = pytest.importorskip("aml_agent.detection.model")
    periods = [*dm.TRAIN_PERIODS, dm.VALIDATION_PERIOD, dm.TEST_PERIOD]
    for (_, end), (start, _) in zip(periods, periods[1:], strict=False):
        assert end < start
    assert set(dm.FEATURE_LABELS) == set(dm.ALL_FEATURES)


def test_metrics():
    np = pytest.importorskip("numpy")
    dm = pytest.importorskip("aml_agent.detection.model")
    y = np.array([1, 0, 1, 0])
    assert dm.average_precision(np.array([0.9, 0.8, 0.7, 0.1]), y) == pytest.approx((1 + 2 / 3) / 2)
    assert dm.average_precision(np.array([0.9, 0.1, 0.8, 0.2]), y) == 1.0
    out = dm.at_threshold(np.array([0.9, 0.8, 0.7, 0.1]), y, 0.75)
    assert (out["flagged"], out["precision"], out["recall"]) == (2, 0.5, 0.5)
    assert dm.best_threshold(np.array([0.9, 0.8, 0.7, 0.1]), y) == 0.7
