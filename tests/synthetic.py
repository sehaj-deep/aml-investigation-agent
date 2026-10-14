"""A tiny, clearly synthetic tool database for CI (no AMLworld rows).

Shape:
- SEED0001 at bank 1 fans out to FAN00001..FAN00006 (US Dollar), and sends one
  Euro payment to FAN00001, all on 2022-09-02.
- FAN00001 forwards to HOP00001 later the same day (for trace_funds).
- SEED0001 has two self-transfers (hidden by default).
- HOP00001 sends to SEED0001 on 2022-09-03 (closes a cycle).
- 150 accounts BULK0000..BULK0149 each pay SEED0001 once (for limit caps).
- One late row on 2022-09-12 (after the primary period): SEED0001 pays LATE0001 in
  Swiss Francs. Hidden from the tools by default.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from aml_agent.data.tooldb import TOOL_DB_NAME

SEED = {"bank_id": 1, "account": "SEED0001"}
LATE_TX_ID = 162
DAY = datetime(2022, 9, 2)


def rows() -> list[tuple]:
    out = []
    tx = 0

    def add(ts, fb, fa, tb, ta, amount, currency, self_transfer=False):
        nonlocal tx
        tx += 1
        out.append(
            (tx, ts, fb, fa, tb, ta, amount, currency, amount, currency, "Wire", self_transfer)
        )

    for i in range(1, 7):
        add(DAY + timedelta(hours=i), 1, "SEED0001", 2, f"FAN0000{i}", 100 * i, "US Dollar")
    add(DAY + timedelta(hours=7), 1, "SEED0001", 2, "FAN00001", 50, "Euro")
    add(DAY + timedelta(hours=8), 2, "FAN00001", 3, "HOP00001", 90, "US Dollar")
    add(DAY + timedelta(hours=9), 1, "SEED0001", 1, "SEED0001", 999, "US Dollar", True)
    add(DAY + timedelta(hours=10), 1, "SEED0001", 1, "SEED0001", 999, "US Dollar", True)
    add(DAY + timedelta(days=1), 3, "HOP00001", 1, "SEED0001", 80, "US Dollar")
    for i in range(150):
        add(DAY + timedelta(days=2, minutes=i), 4, f"BULK{i:04d}", 1, "SEED0001", 1, "Yuan")
    add(datetime(2022, 9, 12, 9), 1, "SEED0001", 3, "LATE0001", 77, "Swiss Franc")
    return out


def build(directory: Path) -> Path:
    path = directory / TOOL_DB_NAME
    path.unlink(missing_ok=True)
    con = duckdb.connect(str(path))
    con.execute(
        """
        CREATE TABLE transactions (
            tx_id BIGINT, ts TIMESTAMP, from_bank INTEGER, from_account VARCHAR,
            to_bank INTEGER, to_account VARCHAR, amount_received DECIMAL(24,6),
            currency_received VARCHAR, amount_paid DECIMAL(24,6), currency_paid VARCHAR,
            payment_format VARCHAR, is_self_transfer BOOLEAN)
        """
    )
    con.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows())
    con.execute(
        "CREATE TABLE banks AS SELECT * FROM (VALUES "
        "(1, 'Synthetic Bank One', 'US'), (2, 'Synthetic Bank Two', 'CA'), "
        "(3, 'Synthetic Bank Three', 'GB'), (4, 'Synthetic Bank Four', 'CN')) "
        "AS t(bank_id, bank_name, jurisdiction)"
    )
    con.close()
    return path
