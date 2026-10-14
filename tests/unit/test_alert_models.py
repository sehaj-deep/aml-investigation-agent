from datetime import datetime

import pytest
from pydantic import ValidationError

from aml_agent.alerts.io import read_alerts, read_truth
from aml_agent.alerts.models import Alert

WINDOW = {"window_start": datetime(2022, 9, 1), "window_end": datetime(2022, 9, 2)}


def test_alert_rejects_label_fields():
    with pytest.raises(ValidationError):
        Alert(alert_id="x", seed_bank=1, seed_account="A", pattern_type="CYCLE", **WINDOW)


def test_alert_rejects_reversed_window():
    with pytest.raises(ValidationError):
        Alert(
            alert_id="x",
            seed_bank=1,
            seed_account="A",
            window_start=datetime(2022, 9, 2),
            window_end=datetime(2022, 9, 1),
        )


@pytest.mark.parametrize("name", ["dev", "eval"])
def test_committed_alert_files_parse_and_carry_no_labels(name):
    alerts = read_alerts(name)
    truth = read_truth(name)
    assert [a.alert_id for a in alerts] == [t.alert_id for t in truth]
    assert set(Alert.model_fields) == {
        "alert_id",
        "seed_bank",
        "seed_account",
        "window_start",
        "window_end",
    }


def test_set_sizes_and_balance():
    for name, per_type in (("dev", 3), ("eval", 5)):
        truth = read_truth(name)
        positives = [t for t in truth if t.label == "positive"]
        assert len(positives) == 8 * per_type
        assert len(truth) == 2 * len(positives)
        counts = {}
        for t in positives:
            counts[t.pattern_type] = counts.get(t.pattern_type, 0) + 1
        assert set(counts.values()) == {per_type}


def test_dev_and_eval_share_no_block_or_seed():
    dev_truth, eval_truth = read_truth("dev"), read_truth("eval")
    assert not {t.block_id for t in dev_truth if t.block_id} & {
        t.block_id for t in eval_truth if t.block_id
    }
    dev_seeds = {(a.seed_bank, a.seed_account) for a in read_alerts("dev")}
    eval_seeds = {(a.seed_bank, a.seed_account) for a in read_alerts("eval")}
    assert not dev_seeds & eval_seeds


def test_benign_windows_copy_their_matched_positive():
    for name in ("dev", "eval"):
        alerts = {a.alert_id: a for a in read_alerts(name)}
        for t in read_truth(name):
            if t.label == "benign":
                a, p = alerts[t.alert_id], alerts[t.matched_to]
                assert (a.window_start, a.window_end) == (p.window_start, p.window_end)
