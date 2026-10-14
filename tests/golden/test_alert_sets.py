"""Sprint 0 Verify: alert seeds follow the seed rule, checked against the data."""

import json
from datetime import timedelta

import pytest

from aml_agent.alerts import generate as gen
from aml_agent.alerts.io import ALERTS_DIR, read_alerts, read_truth
from tests.conftest import scalar

pytestmark = pytest.mark.data

LABELED_ACCOUNT = """
    SELECT count(*) FROM transactions
    WHERE is_laundering AND ((from_bank = ? AND from_account = ?)
                          OR (to_bank = ? AND to_account = ?))
"""


@pytest.mark.parametrize("name", ["dev", "eval"])
def test_positive_seeds_follow_seed_rule(con, name):
    alerts = {a.alert_id: a for a in read_alerts(name)}
    for t in read_truth(name):
        if t.label != "positive":
            continue
        a = alerts[t.alert_id]
        key = [a.seed_bank, a.seed_account]
        blocks = con.execute(
            "SELECT DISTINCT block_id FROM pattern_accounts WHERE bank_id = ? AND account = ?",
            key,
        ).fetchall()
        assert blocks == [(t.block_id,)]
        in_other = scalar(
            con,
            """
            SELECT count(*) FROM other_laundering JOIN transactions USING (tx_id)
            WHERE (from_bank = ? AND from_account = ?) OR (to_bank = ? AND to_account = ?)
            """,
            key * 2,
        )
        assert in_other == 0
        n_tx, first_ts, last_ts = con.execute(
            "SELECT n_tx, first_ts, last_ts FROM pattern_blocks WHERE block_id = ?",
            [t.block_id],
        ).fetchone()
        assert n_tx >= 2
        assert a.window_start == first_ts - timedelta(hours=24)
        assert a.window_end == last_ts + timedelta(hours=24)


@pytest.mark.parametrize("name", ["dev", "eval"])
def test_benign_seeds_touch_no_labeled_row_and_are_active(con, name):
    alerts = {a.alert_id: a for a in read_alerts(name)}
    for t in read_truth(name):
        if t.label != "benign":
            continue
        a = alerts[t.alert_id]
        key = [a.seed_bank, a.seed_account]
        assert scalar(con, LABELED_ACCOUNT, key * 2) == 0
        active = scalar(
            con,
            """
            SELECT count(*) FROM transactions
            WHERE NOT is_self_transfer AND ts BETWEEN ? AND ?
              AND ((from_bank = ? AND from_account = ?) OR (to_bank = ? AND to_account = ?))
            """,
            [a.window_start, a.window_end, *key, *key],
        )
        assert active >= 1


def test_generation_is_deterministic(con):
    manifest = json.loads((ALERTS_DIR / "manifest.json").read_text())
    sets = gen.generate(con, seed=manifest["seed"])
    for name, s in sets.items():
        assert s.alerts == read_alerts(name)
        assert s.truth == read_truth(name)
