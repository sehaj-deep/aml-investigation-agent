"""Golden numbers for the accounts and banks tables (PRD Appendix A, section 10)."""

import pytest

from tests.conftest import scalar
from tests.golden import expected as E

pytestmark = pytest.mark.data


def test_unique_account_numbers(con):
    assert scalar(con, "SELECT count(DISTINCT account) FROM accounts") == E.ACCOUNT_NUMBERS_UNIQUE


def test_duplicated_account_numbers(con):
    n = scalar(
        con,
        "SELECT count(*) FROM (SELECT account FROM accounts GROUP BY 1 HAVING count(*) > 1)",
    )
    assert n == E.ACCOUNT_NUMBERS_DUPLICATED


def test_bank_account_pairs_are_unique(con):
    assert scalar(con, "SELECT count(*) FROM accounts") == scalar(
        con, "SELECT count(*) FROM (SELECT DISTINCT bank_id, account FROM accounts)"
    )


def test_each_bank_has_one_name(con):
    n = scalar(
        con,
        "SELECT max(n) FROM (SELECT count(DISTINCT bank_name) n FROM accounts GROUP BY bank_id)",
    )
    assert n == 1


def test_country_labels(con):
    n = scalar(con, "SELECT count(DISTINCT bank_label) FROM banks WHERE bank_label <> 'US-style'")
    assert n == E.COUNTRY_LABELS


def test_us_style_pool(con):
    accounts, names, bank_ids = con.execute(
        """
        SELECT count(DISTINCT a.account), count(DISTINCT b.bank_name), count(DISTINCT b.bank_id)
        FROM accounts a JOIN banks b USING (bank_id)
        WHERE b.bank_label = 'US-style'
        """
    ).fetchone()
    assert accounts == E.US_STYLE_ACCOUNTS
    assert names == E.US_STYLE_NAMES
    assert bank_ids == E.US_STYLE_BANK_IDS


def test_every_bank_has_a_jurisdiction(con):
    assert scalar(con, "SELECT count(*) FROM banks WHERE jurisdiction IS NULL") == 0


@pytest.mark.parametrize("label", list(E.CURRENCY_SHARE_BY_LABEL))
def test_currency_share_by_label(con, label):
    currency, pct = E.CURRENCY_SHARE_BY_LABEL[label]
    share = scalar(
        con,
        """
        SELECT 100.0 * count(*) FILTER (t.currency_paid = ?) / count(*)
        FROM transactions t JOIN banks b ON b.bank_id = t.from_bank
        WHERE b.bank_label = ?
        """,
        [currency, label],
    )
    assert round(share) == pct
