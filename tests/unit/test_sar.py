"""SAR draft: code-built facts, checks on the narrative, and the exported document."""

from __future__ import annotations

import asyncio
import json

from aml_agent.agent import sar
from aml_agent.llm.base import ChatResponse
from aml_agent.llm.scripted import ScriptedProvider

EM_DASH = chr(0x2014)


def evidence(tx_id, ts, src, dst, amount, currency):
    return {
        "tx_id": tx_id,
        "timestamp": ts,
        "from_bank": src[0],
        "from_account": src[1],
        "to_bank": dst[0],
        "to_account": dst[1],
        "amount_paid": amount,
        "currency_paid": currency,
    }


SUBJECT = ("1", "SEED0001")
CASE = {
    "case_id": "case-sar",
    "status": "escalated",
    "alert": {
        "alert_id": "ALR-00001",
        "seed_bank": 1,
        "seed_account": "SEED0001",
        "window_start": "2022-09-02T00:00:00",
        "window_end": "2022-09-04T00:00:00",
        "detection_factors": [{"feature": "format_ach", "label": "payment by ACH"}],
    },
    "draft": {
        "pattern_hypothesis": "fan-out",
        "summary": "A0 pays two new accounts.",
        "recommended_action": "escalate",
        "limitations": "Customer background unknown.",
        "evidence": [
            evidence(2, "2022-09-02T11:00", SUBJECT, ("2", "B"), "200.000000", "US Dollar"),
            evidence(1, "2022-09-02T10:00", SUBJECT, ("2", "A"), "100.000000", "US Dollar"),
            evidence(9, "2022-09-02T09:00", ("3", "C"), SUBJECT, "50.500000", "Euro"),
        ],
    },
    "analysis": {
        "aliases": {"A0": [1, "SEED0001"], "A1": [2, "A"], "A2": [2, "B"], "A3": [3, "C"]},
        "risk": {"subject": {"rules": ["R2", "R3"]}, "top_counterparty": None},
    },
    "case_graph": {"nodes": [{"label": "A0", "jurisdiction": "US"}]},
    "decisions": [
        {"action": "escalate", "reviewer": "ana", "role": "analyst", "reason": "Fan-out."},
        {
            "action": "confirm_escalation",
            "reviewer": "sam",
            "role": "supervisor",
            "reason": "Agreed.",
            "decided_at": "2026-10-14T10:00:00+00:00",
        },
    ],
}


def test_facts_are_built_by_code():
    f = sar.facts(CASE)
    assert [t["tx_id"] for t in f["transactions"]] == [9, 1, 2]  # time order
    assert f["totals"] == {
        "sent_by_subject": {"US Dollar": "300"},
        "received_by_subject": {"Euro": "50.5"},
    }
    assert f["subject"] == {"bank_id": "1", "account": "SEED0001", "jurisdiction": "US"}
    assert [r["rule"] for r in f["red_flags"]] == [
        "Flow-through activity",
        "Predominantly new counterparties",
    ]
    assert f["filing_due"] == "2026-11-13"  # 30 days after the confirmed escalation
    assert f["decisions"][1]["decided_at"] == "2026-10-14T10:00"
    text = sar.facts_text(f)
    assert "tx 1 2022-09-02T10:00 1/SEED0001 -> 2/A: 100 US Dollar" in text


def test_check_flags_unknown_citations_and_amounts():
    f = sar.facts(CASE)
    ok = {k: "A0 paid 100.00 US Dollar (tx 1); in total 300 US Dollar." for k in sar.SECTIONS}
    assert sar.check(ok, f) == []
    bad = dict(ok, activity=f"A0 paid 1,234.50 Euro (tx 77) {EM_DASH} late.")
    warnings = sar.check(bad, f)
    assert "tx 77 is cited but is not in the evidence" in warnings
    assert "the amount 1,234.50 does not match any evidence amount or total" in warnings
    assert "the narrative contains a long dash" in warnings
    filed = dict(ok, conclusion="The SAR has been filed for regulatory review.")
    assert any("draft awaiting approval" in w for w in sar.check(filed, f))
    # Times are not amounts: "10:00:20.846865" or "2022-09-02" raise no warning.
    times = dict(ok, conclusion="Escalated at 2026-10-15T01:10:20.846865 by the analyst.")
    assert sar.check(times, f) == []


class RetryModel:
    provider, model = "fake", "fake-sar"

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return ChatResponse("Here is the report: not JSON", [], 0, 50, 5)
        body = {k: f"Section {k}: the subject paid 200.00 US Dollar (tx 2)." for k in sar.SECTIONS}
        return ChatResponse(json.dumps(body), [], 0, 50, 5)


def test_draft_retries_once_and_is_checked():
    model = RetryModel()
    out = asyncio.run(sar.draft(model, CASE))
    assert model.calls == 2
    assert set(out["sections"]) == set(sar.SECTIONS)
    assert out["warnings"] == []
    assert out["tokens"] == 110


def test_scripted_draft_and_markdown_export():
    out = asyncio.run(sar.draft(ScriptedProvider(), CASE))
    assert out["warnings"] == [] and "tx 9" in out["sections"]["activity"]
    doc = sar.markdown({**out, "version_no": 2, "status": "approved", "approved_by": "sam"})
    assert doc.startswith("# Suspicious activity report: narrative draft")
    assert "Not filed with any authority" in doc
    assert "| tx 1 | 2022-09-02T10:00 | 1/SEED0001 | 2/A | 100 US Dollar |" in doc
    assert "Filing due: 2026-11-13" in doc and "approved by sam" in doc
