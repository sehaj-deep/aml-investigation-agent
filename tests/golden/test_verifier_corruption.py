"""Sprint 2 Verify: the citation verifier on real Parquet slices (no mocks).

Clean cases are built straight from the Parquet rows of each dev positive's
pattern block. Each corruption (one amount, ID, date or party changed) must be
flagged, and no clean case may raise a false alarm.
"""

import copy
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from aml_agent.alerts.io import read_truth
from aml_agent.verify.citations import CitationVerifier

pytestmark = pytest.mark.data


@pytest.fixture(scope="module")
def verifier(con):
    return CitationVerifier(con)


@pytest.fixture(scope="module")
def clean_cases(con) -> list[dict]:
    cases = []
    for t in read_truth("dev"):
        if t.label != "positive":
            continue
        rows = con.execute(
            """
            SELECT tx_id, from_bank, from_account, to_bank, to_account,
                   amount_paid, currency_paid, ts
            FROM pattern_transactions JOIN transactions USING (tx_id)
            WHERE block_id = ? ORDER BY tx_id
            """,
            [t.block_id],
        ).fetchall()
        evidence = [
            {
                "tx_id": r[0],
                "from_bank": str(r[1]),
                "from_account": r[2],
                "to_bank": str(r[3]),
                "to_account": r[4],
                "amount_paid": format(r[5], "f"),
                "currency_paid": r[6],
                "timestamp": r[7].strftime("%Y-%m-%dT%H:%M"),
            }
            for r in rows
        ]
        cases.append({"case_id": t.alert_id, "evidence": evidence})
    assert len(cases) == 24
    return cases


def _other_account(con, not_this: str) -> str:
    return con.execute(
        "SELECT to_account FROM transactions WHERE to_account <> ? ORDER BY tx_id LIMIT 1",
        [not_this],
    ).fetchone()[0]


def corruptions(con, case: dict) -> list[tuple[str, dict, list]]:
    """(name, corrupted case, cited ids) for one changed field each."""
    e0 = case["evidence"][0]
    max_tx = con.execute("SELECT max(tx_id) FROM transactions").fetchone()[0]
    out = []

    def variant(name, mutate, cited=None):
        c = copy.deepcopy(case)
        mutate(c["evidence"][0])
        ids = [e["tx_id"] for e in c["evidence"]] if cited is None else cited
        out.append((name, c, ids))

    variant("amount", lambda e: e.update(amount_paid=str(Decimal(e["amount_paid"]) + 1)))
    variant(
        "amount_cent",
        lambda e: e.update(amount_paid=str(Decimal(e["amount_paid"]) + Decimal("0.01"))),
    )
    variant(
        "currency",
        lambda e: e.update(currency_paid="Bitcoin" if e["currency_paid"] != "Bitcoin" else "Euro"),
    )
    variant("tx_id_invented", lambda e: e.update(tx_id=max_tx + 1000))
    variant(
        "tx_id_swapped",
        lambda e: e.update(tx_id=e["tx_id"] + 1 if e["tx_id"] < max_tx else e["tx_id"] - 1),
    )
    ts = datetime.fromisoformat(e0["timestamp"])
    variant(
        "date_minute",
        lambda e: e.update(timestamp=(ts + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")),
    )
    variant(
        "date_day",
        lambda e: e.update(timestamp=(ts - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")),
    )
    variant("from_account", lambda e: e.update(from_account=_other_account(con, e["from_account"])))
    variant("to_account", lambda e: e.update(to_account=_other_account(con, e["to_account"])))
    variant("to_bank", lambda e: e.update(to_bank=str(int(e["to_bank"]) + 1)))
    variant("from_bank", lambda e: e.update(from_bank=str(int(e["from_bank"]) + 1)))
    ids = [e["tx_id"] for e in case["evidence"]]
    out.append(("cited_invented_id", copy.deepcopy(case), [*ids, max_tx + 5000]))
    return out


def test_clean_cases_raise_no_false_alarms(verifier, clean_cases):
    for case in clean_cases:
        result = verifier.verify_case(case)
        assert result.faithful, (case["case_id"], result.as_dict())
        assert result.warnings() == []


def test_every_corruption_is_flagged(con, verifier, clean_cases):
    total = 0
    missed = []
    for case in clean_cases:
        for name, corrupted, cited in corruptions(con, case):
            total += 1
            result = verifier.verify_case(corrupted, cited_tx_ids=cited)
            if result.faithful or not result.warnings():
                missed.append((case["case_id"], name))
    assert total == 24 * 12
    assert missed == []


def test_mismatch_names_the_field(con, verifier, clean_cases):
    case = clean_cases[0]
    for name, corrupted, cited in corruptions(con, case):
        result = verifier.verify_case(corrupted, cited_tx_ids=cited)
        if name in ("amount", "amount_cent"):
            assert "amount_paid" in result.failures[0]["mismatches"]
        elif name in ("date_minute", "date_day"):
            assert "timestamp" in result.failures[0]["mismatches"]
        elif name in ("from_account", "to_account", "to_bank", "from_bank", "currency"):
            field = "currency_paid" if name == "currency" else name
            assert field in result.failures[0]["mismatches"]
        elif name == "tx_id_invented":
            assert result.failures[0]["exists"] is False
        elif name == "cited_invented_id":
            assert result.missing_tx_ids


def test_grounding_is_reported_separately(verifier, clean_cases):
    case = clean_cases[0]
    ids = [e["tx_id"] for e in case["evidence"]]
    result = verifier.verify_case(case, cited_tx_ids=ids, seen_tx_ids=ids[1:])
    assert result.faithful and not result.grounded
    assert result.ungrounded_tx_ids == ids[:1]
