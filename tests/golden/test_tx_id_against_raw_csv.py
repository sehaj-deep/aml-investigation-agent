"""Independent check that tx_id is the 1-based row number of the raw CSV.

Streams the raw file with the csv module (never pandas) and compares the first,
last and 1,000 seeded-random rows with the Parquet rows of the same tx_id.
"""

import csv
import random
from datetime import datetime
from decimal import Decimal

import pytest

from aml_agent import config
from tests.golden import expected as E

pytestmark = pytest.mark.data


def test_sampled_rows_match_raw_file(con):
    rng = random.Random(20261014)
    wanted = {1, E.TRANSACTIONS, *rng.sample(range(1, E.TRANSACTIONS + 1), 1000)}
    raw: dict[int, list[str]] = {}
    with (config.data_dir() / config.TRANS_FILE).open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)  # header
        for row_number, row in enumerate(reader, start=1):
            if row_number in wanted:
                raw[row_number] = row
        assert row_number == E.TRANSACTIONS
    assert len(raw) == len(wanted)

    ids = sorted(wanted)
    rows = con.execute(
        """
        SELECT tx_id, ts, from_bank_raw, from_account, to_bank_raw, to_account,
               amount_received, currency_received, amount_paid, currency_paid,
               payment_format, is_laundering
        FROM transactions WHERE tx_id IN (SELECT unnest(?)) ORDER BY tx_id
        """,
        [ids],
    ).fetchall()
    assert [r[0] for r in rows] == ids
    for r in rows:
        f = raw[r[0]]
        assert r[1] == datetime.strptime(f[0], "%Y/%m/%d %H:%M")
        assert (r[2], r[3], r[4], r[5]) == (f[1], f[2], f[3], f[4])
        assert r[6] == Decimal(f[5]) and r[7] == f[6]
        assert r[8] == Decimal(f[7]) and r[9] == f[8]
        assert r[10] == f[9]
        assert r[11] == (f[10] == "1")
