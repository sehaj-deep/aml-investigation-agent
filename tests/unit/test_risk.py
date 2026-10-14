"""Rules-based risk indicators: rules, case scoring, and the behavior tool (CI)."""

import pytest

from aml_agent.analysis.risk import HIGH_BAND, account_score, band, case_risk, describe, fired_rules
from aml_agent.tools.graph import GraphTools
from tests import synthetic

QUIET = {
    "n_transfers": 4,
    "receives_and_pays": False,
    "currency_switch": False,
    "new_counterparty_share": 0.2,
    "one_time_counterparty_share": 0.2,
    "period_activity_share": 0.3,
    "onward_within_24h_share": 0.0,
}


def test_each_rule_fires_on_its_signal():
    assert fired_rules(QUIET) == []
    assert fired_rules({**QUIET, "currency_switch": True}) == ["R1"]
    assert fired_rules({**QUIET, "receives_and_pays": True}) == ["R2"]
    assert fired_rules({**QUIET, "new_counterparty_share": 0.9}) == ["R3"]
    assert fired_rules({**QUIET, "one_time_counterparty_share": 0.7}) == ["R4"]
    assert fired_rules({**QUIET, "period_activity_share": 0.7}) == ["R5"]
    assert fired_rules({**QUIET, "onward_within_24h_share": 0.5}) == ["R6"]
    assert fired_rules({**QUIET, "n_transfers": 0, "currency_switch": True}) == []


def test_scores_and_bands():
    assert account_score(["R1", "R2"]) == 4
    assert band(HIGH_BAND) == "high" and band(5) == "medium" and band(4) == "low"


def test_case_risk_adds_the_riskiest_counterparty():
    hot = {
        **QUIET,
        "currency_switch": True,
        "receives_and_pays": True,
        "period_activity_share": 0.9,
    }
    risk = case_risk({**QUIET, "new_counterparty_share": 1.0}, {"A3": QUIET, "A5": hot})
    assert risk["subject"] == {"score": 1, "rules": ["R3"]}
    assert risk["top_counterparty"] == {"label": "A5", "score": 5, "rules": ["R1", "R2", "R5"]}
    assert (risk["score"], risk["band"]) == (6, "medium")
    text = describe(risk)
    assert "score 6, band MEDIUM" in text
    assert "A5: score 5: R1 Currency conversion pass-through (+3)" in text


def test_case_risk_without_counterparties():
    risk = case_risk(QUIET, {})
    assert risk["score"] == 0 and risk["top_counterparty"] is None and risk["band"] == "low"


@pytest.fixture(scope="module")
def tools(tmp_path_factory):
    t = GraphTools(synthetic.build(tmp_path_factory.mktemp("riskdb")))
    yield t
    t.close()


def test_behavior_tool_on_synthetic_seed(tools):
    out = tools.get_account_behavior(
        **synthetic.SEED, window_start="2022-09-01T00:00", window_end="2022-09-10T00:00"
    )
    s = out["signals"]
    assert s["receives_and_pays"] is True
    assert s["in_currencies"] == ["US Dollar", "Yuan"] and s["out_currencies"] == [
        "Euro",
        "US Dollar",
    ]
    assert s["currency_switch"] is False
    assert s["new_counterparty_share"] == 1.0  # nothing before the window
    assert s["one_time_counterparty_share"] == 1.0
    assert s["onward_within_24h_share"] == 0.0  # money arrives after the seed's payments
    assert out["rules"] == ["R2", "R3", "R4", "R5"] and out["score"] == 4


def test_behavior_tool_hides_late_rows(tools):
    out = tools.get_account_behavior(bank_id=3, account="LATE0001")
    assert out["signals"]["n_transfers"] == 0 and out["rules"] == []
