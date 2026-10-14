"""Detection features on the synthetic tool database, and the model's split and metric.

The model tests need the optional detection dependencies (requirements-detection.txt)
and are skipped without them.
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import pytest

from aml_agent.detection.features import FEATURES, build_currency_stats, build_features
from tests import synthetic

START, END = datetime(2022, 9, 2), datetime(2022, 9, 3, 23, 59)


@pytest.fixture()
def features(tmp_path):
    path = synthetic.build(tmp_path)
    con = duckdb.connect()
    con.execute(f"ATTACH '{path.as_posix()}' AS src (READ_ONLY)")
    con.execute("CREATE VIEW transactions AS SELECT * FROM src.transactions")
    build_currency_stats(con)
    build_features(con, START, END)
    yield con
    con.close()


def row(con, account: str) -> dict:
    cols = ", ".join(FEATURES)
    values = con.execute(f"SELECT {cols} FROM features WHERE a = ?", [account]).fetchone()
    return dict(zip(FEATURES, values, strict=True))


def test_every_feature_is_a_column(features):
    cols = [r[0] for r in features.execute("DESCRIBE features").fetchall()]
    assert cols == ["b", "a", *FEATURES]
    assert not {"is_laundering", "payment_format"} & set(cols)


def test_one_row_per_active_account_without_self_transfers(features):
    n, distinct = features.execute(
        "SELECT count(*), count(DISTINCT (b, a)) FROM features"
    ).fetchone()
    assert n == distinct
    seed = row(features, "SEED0001")
    # 7 payments out and HOP00001's payment in; the two self-transfers are ignored.
    assert (seed["n_out"], seed["n_in"]) == (7, 1)
    assert seed["receivers"] == 6
    assert seed["currencies_out"] == 2
    assert seed["reciprocal_counterparties"] == 0


def test_late_rows_are_outside_the_period(features):
    assert features.execute("SELECT count(*) FROM features WHERE a = 'LATE0001'").fetchone()[0] == 0


def test_split_periods_are_ordered_and_disjoint():
    dm = pytest.importorskip("aml_agent.detection.model")
    periods = [*dm.TRAIN_PERIODS, dm.VALIDATION_PERIOD, dm.TEST_PERIOD]
    for (_, end), (start, _) in zip(periods, periods[1:], strict=False):
        assert end < start
    assert set(dm.FEATURE_LABELS) == set(FEATURES)


def test_average_precision():
    np = pytest.importorskip("numpy")
    dm = pytest.importorskip("aml_agent.detection.model")
    y = np.array([1, 0, 1, 0])
    assert dm.average_precision(np.array([0.9, 0.8, 0.7, 0.1]), y) == pytest.approx((1 + 2 / 3) / 2)
    assert dm.average_precision(np.array([0.9, 0.1, 0.8, 0.2]), y) == 1.0
