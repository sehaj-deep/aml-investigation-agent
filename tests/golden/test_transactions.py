"""Golden numbers for the transactions table (PRD Appendix A)."""

import pytest

from tests.conftest import scalar
from tests.golden import expected as E

pytestmark = pytest.mark.data


def test_row_count(con):
    assert scalar(con, "SELECT count(*) FROM transactions") == E.TRANSACTIONS


def test_tx_id_is_dense_and_unique(con):
    row = con.execute(
        "SELECT min(tx_id), max(tx_id), count(DISTINCT tx_id) FROM transactions"
    ).fetchone()
    assert row == (1, E.TRANSACTIONS, E.TRANSACTIONS)


def test_labeled(con):
    labeled = scalar(con, "SELECT count(*) FROM transactions WHERE is_laundering")
    assert labeled == E.LABELED
    assert round(E.TRANSACTIONS / labeled) == E.ONE_IN


def test_time_span(con):
    assert con.execute("SELECT min(ts), max(ts) FROM transactions").fetchone() == (
        E.FIRST_TS,
        E.LAST_TS,
    )


def test_background_rows_per_day(con):
    lo, hi = con.execute(
        """
        SELECT min(n), max(n) FROM (
            SELECT ts::DATE d, count(*) n FROM transactions
            WHERE ts < TIMESTAMP '2022-09-11' GROUP BY d)
        """
    ).fetchone()
    assert round(lo / 1000) == E.BACKGROUND_MIN_ROWS_PER_DAY_K
    assert round(hi / 1e6, 1) == E.BACKGROUND_MAX_ROWS_PER_DAY_M


def test_tail_after_09_10(con):
    total, labeled, unlabeled, unlabeled_ach = con.execute(
        """
        SELECT count(*), count(*) FILTER (is_laundering),
               count(*) FILTER (NOT is_laundering),
               count(*) FILTER (NOT is_laundering AND payment_format = 'ACH')
        FROM transactions WHERE ts >= TIMESTAMP '2022-09-11'
        """
    ).fetchone()
    assert total == E.TAIL_ROWS
    assert labeled == E.TAIL_LABELED
    assert unlabeled == E.TAIL_UNLABELED
    assert unlabeled_ach == E.TAIL_UNLABELED
    first_day = scalar(con, "SELECT count(*) FROM transactions WHERE ts::DATE = '2022-09-11'")
    last_day = scalar(con, "SELECT count(*) FROM transactions WHERE ts::DATE = '2022-09-18'")
    assert (first_day, last_day) == (E.TAIL_FIRST_DAY_ROWS, E.TAIL_LAST_DAY_ROWS)


def test_file_not_sorted_by_time(con):
    out_of_order = scalar(
        con,
        """
        SELECT count(*) FROM (
            SELECT ts < lag(ts) OVER (ORDER BY tx_id) AS back FROM transactions)
        WHERE back
        """,
    )
    assert out_of_order > 0


def test_chronological_cutoffs(con):
    c60, c80 = con.execute(
        "SELECT quantile_disc(ts, 0.6), quantile_disc(ts, 0.8) FROM transactions"
    ).fetchone()
    assert (c60, c80) == (E.CUTOFF_60, E.CUTOFF_80)


def test_payment_formats(con):
    rows = dict(
        con.execute("SELECT payment_format, count(*) FROM transactions GROUP BY 1").fetchall()
    )
    assert rows == E.PAYMENT_FORMATS


def test_top_currencies(con):
    # Appendix A does not name the column; its counts are the receiving currency.
    rows = con.execute(
        "SELECT currency_received, count(*) FROM transactions GROUP BY 1 ORDER BY 2 DESC LIMIT 6"
    ).fetchall()
    assert dict(rows) == E.TOP_CURRENCIES


def test_self_transfers(con):
    assert (
        scalar(con, "SELECT count(*) FROM transactions WHERE is_self_transfer") == E.SELF_TRANSFERS
    )


def test_bank_ids(con):
    n = scalar(
        con,
        "SELECT count(DISTINCT b) FROM (SELECT from_bank b FROM transactions "
        "UNION ALL SELECT to_bank FROM transactions)",
    )
    assert n == E.BANK_IDS
    assert scalar(con, "SELECT count(*) FROM banks") == E.BANK_IDS


def test_banks_with_two_spellings(con):
    n = scalar(
        con,
        """
        SELECT count(*) FROM (
            SELECT b FROM (
                SELECT from_bank b, from_bank_raw r FROM transactions
                UNION SELECT to_bank, to_bank_raw FROM transactions)
            GROUP BY b HAVING count(DISTINCT r) = 2)
        """,
    )
    assert n == E.BANKS_WITH_TWO_SPELLINGS


def test_no_account_split_by_bank_spelling(con):
    # Each (integer bank, account) pair appears under exactly one raw spelling.
    n = scalar(
        con,
        """
        SELECT count(*) FROM (
            SELECT b, a FROM (
                SELECT from_bank b, from_account a, from_bank_raw r FROM transactions
                UNION SELECT to_bank, to_account, to_bank_raw FROM transactions)
            GROUP BY b, a HAVING count(DISTINCT r) > 1)
        """,
    )
    assert n == 0


def test_account_pairs_in_transactions(con):
    n = scalar(
        con,
        "SELECT count(*) FROM (SELECT from_bank, from_account FROM transactions "
        "UNION SELECT to_bank, to_account FROM transactions)",
    )
    assert n == E.TX_ACCOUNT_PAIRS


def test_labeled_ach(con):
    n = scalar(
        con, "SELECT count(*) FROM transactions WHERE is_laundering AND payment_format = 'ACH'"
    )
    assert n >= E.LABELED_ACH_AT_LEAST
