"""Golden numbers for pattern blocks, Other laundering and seed eligibility."""

from collections import Counter, defaultdict

import pytest

from tests.conftest import scalar
from tests.golden import expected as E

pytestmark = pytest.mark.data

# Open definition questions (see NOTES_FOR_YOU.md). Expected values are unchanged;
# strict xfail makes the test fail loudly if it starts passing.
PENDING = "definition question pending owner decision; expected value not edited"


def by_type(con, where: str = "TRUE") -> dict:
    return dict(
        con.execute(
            f"SELECT pattern_type, count(*) FROM pattern_blocks WHERE {where} GROUP BY 1"
        ).fetchall()
    )


def test_blocks(con):
    assert scalar(con, "SELECT count(*) FROM pattern_blocks") == E.PATTERN_BLOCKS
    assert by_type(con) == E.PATTERN_BLOCKS_BY_TYPE


def test_pattern_rows_each_match_one_transaction(con):
    rows, distinct_tx, labeled = con.execute(
        """
        SELECT count(*), count(DISTINCT pt.tx_id), count(*) FILTER (t.is_laundering)
        FROM pattern_transactions pt JOIN transactions t USING (tx_id)
        """
    ).fetchone()
    assert rows == distinct_tx == labeled == E.PATTERN_ROWS


def test_pattern_row_formats(con):
    rows = con.execute(
        "SELECT payment_format, count(*) FROM pattern_transactions "
        "JOIN transactions USING (tx_id) GROUP BY 1"
    ).fetchall()
    assert dict(rows) == E.PATTERN_ROW_FORMATS


def test_single_and_multi_row_blocks(con):
    assert sum(by_type(con, "n_tx = 1").values()) == E.SINGLE_ROW_BLOCKS
    assert by_type(con, "n_tx = 1") == E.SINGLE_ROW_BLOCKS_BY_TYPE
    assert sum(by_type(con, "n_tx >= 2").values()) == E.MULTI_ROW_BLOCKS
    assert by_type(con, "n_tx >= 2") == E.MULTI_ROW_BLOCKS_BY_TYPE


def test_single_row_blocks_are_degree_one(con):
    # Header parameter is 1 where present; BIPARTITE has no parameter.
    bad = scalar(
        con,
        "SELECT count(*) FROM pattern_blocks "
        "WHERE n_tx = 1 AND param_value IS NOT NULL AND param_value <> 1",
    )
    assert bad == 0


@pytest.mark.xfail(strict=True, reason=PENDING + " (median 6.5 vs 7)")
def test_block_sizes(con):
    lo, hi, med = con.execute(
        "SELECT min(n_tx), max(n_tx), median(n_tx) FROM pattern_blocks"
    ).fetchone()
    assert (lo, hi, med) == (E.BLOCK_SIZE_MIN, E.BLOCK_SIZE_MAX, E.BLOCK_SIZE_MEDIAN)
    med_accounts = scalar(
        con,
        "SELECT median(n) FROM (SELECT block_id, count(*) n FROM pattern_accounts GROUP BY 1)",
    )
    assert med_accounts == E.BLOCK_ACCOUNTS_MEDIAN


def test_pattern_accounts(con):
    total, many = con.execute(
        """
        SELECT count(*), count(*) FILTER (nb > 1) FROM (
            SELECT bank_id, account, count(DISTINCT block_id) nb
            FROM pattern_accounts GROUP BY 1, 2)
        """
    ).fetchone()
    assert total == E.PATTERN_ACCOUNTS
    assert many == E.PATTERN_ACCOUNTS_IN_MANY_BLOCKS


def test_multi_row_blocks_sharing_an_account(con):
    n = scalar(
        con,
        """
        WITH shared AS (
            SELECT bank_id, account FROM pattern_accounts
            GROUP BY 1, 2 HAVING count(DISTINCT block_id) > 1)
        SELECT count(DISTINCT pa.block_id)
        FROM pattern_accounts pa JOIN shared USING (bank_id, account)
        JOIN pattern_blocks b USING (block_id) WHERE b.n_tx >= 2
        """,
    )
    assert n == E.MULTI_ROW_BLOCKS_SHARING_AN_ACCOUNT


def test_seed_eligible_blocks(con):
    rows = con.execute(
        """
        SELECT b.pattern_type, count(DISTINCT s.block_id)
        FROM seed_eligible s JOIN pattern_blocks b USING (block_id) GROUP BY 1
        """
    ).fetchall()
    assert sum(n for _, n in rows) == E.SEED_ELIGIBLE_BLOCKS
    assert dict(rows) == E.SEED_ELIGIBLE_BLOCKS_BY_TYPE


def test_other_laundering(con):
    n, first, last = con.execute(
        "SELECT count(*), min(ts)::DATE, max(ts)::DATE "
        "FROM other_laundering JOIN transactions USING (tx_id)"
    ).fetchone()
    assert n == E.OTHER_LAUNDERING
    assert first == E.OTHER_FIRST_DAY.date()
    assert last == E.OTHER_LAST_DAY.date()
    assert n + E.PATTERN_ROWS == E.LABELED


def test_other_touching_pattern_accounts(con):
    n = scalar(
        con,
        """
        WITH pa AS (SELECT DISTINCT bank_id, account FROM pattern_accounts)
        SELECT count(*) FROM other_laundering o JOIN transactions t USING (tx_id)
        WHERE (t.from_bank, t.from_account) IN (SELECT (bank_id, account) FROM pa)
           OR (t.to_bank, t.to_account) IN (SELECT (bank_id, account) FROM pa)
        """,
    )
    assert n == E.OTHER_TOUCHING_PATTERN_ACCOUNT


SENDER_EARLIER_RECEIVED = """
    SELECT count(*) FROM {rows} r JOIN transactions t USING (tx_id)
    WHERE EXISTS (
        SELECT 1 FROM transactions l
        WHERE l.is_laundering AND l.to_bank = t.from_bank
          AND l.to_account = t.from_account AND l.ts < t.ts)
"""


def test_other_sender_earlier_received_labeled(con):
    n = scalar(con, SENDER_EARLIER_RECEIVED.format(rows="other_laundering"))
    assert n == E.OTHER_SENDER_EARLIER_RECEIVED_LABELED


@pytest.mark.xfail(strict=True, reason=PENDING + " (1406 vs 1395)")
def test_pattern_sender_earlier_received_labeled(con):
    n = scalar(con, SENDER_EARLIER_RECEIVED.format(rows="pattern_transactions"))
    assert n == E.PATTERN_ROWS_SENDER_EARLIER_RECEIVED_LABELED


def _other_groups(con) -> list[dict]:
    """Group Other-laundering rows that share an account (connected components)."""
    rows = con.execute(
        """
        SELECT tx_id, from_bank, from_account, to_bank, to_account, payment_format
        FROM other_laundering JOIN transactions USING (tx_id) ORDER BY tx_id
        """
    ).fetchall()
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _, fb, fa, tb, ta, _ in rows:
        parent[find((fb, fa))] = find((tb, ta))
    groups: dict = defaultdict(lambda: {"rows": 0, "senders": set(), "receivers": set(), "fmt": []})
    for _, fb, fa, tb, ta, fmt in rows:
        g = groups[find((fb, fa))]
        g["rows"] += 1
        g["senders"].add((fb, fa))
        g["receivers"].add((tb, ta))
        g["fmt"].append(fmt)
    return list(groups.values())


def test_other_laundering_structure(con):
    groups = _other_groups(con)
    assert len(groups) == E.OTHER_GROUPS
    isolated = [g for g in groups if g["rows"] == 1]
    assert len(isolated) == E.OTHER_ISOLATED
    assert dict(Counter(g["fmt"][0] for g in isolated)) == E.OTHER_ISOLATED_BY_FORMAT
    larger = sorted((g for g in groups if g["rows"] > 1), key=lambda g: -g["rows"])
    assert len(larger) == E.OTHER_LARGER_GROUPS

    def shape(g):
        return {"rows": g["rows"], "senders": len(g["senders"]), "receivers": len(g["receivers"])}

    assert shape(larger[0]) == E.OTHER_LARGEST_GROUP
    assert shape(larger[1]) == E.OTHER_SECOND_GROUP


@pytest.mark.xfail(strict=True, reason=PENDING + " (41 vs 39)")
def test_blocks_by_country(con):
    one_country, canada = con.execute(
        """
        WITH labels AS (
            SELECT pa.block_id, b.bank_label
            FROM pattern_accounts pa JOIN banks b USING (bank_id))
        SELECT
            (SELECT count(*) FROM (SELECT block_id FROM labels GROUP BY 1
                                   HAVING count(DISTINCT bank_label) = 1)),
            (SELECT count(DISTINCT block_id) FROM labels WHERE bank_label = 'Canada')
        """
    ).fetchone()
    assert one_country == E.BLOCKS_IN_ONE_COUNTRY
    assert canada == E.BLOCKS_TOUCHING_CANADA
