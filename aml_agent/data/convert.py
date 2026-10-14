"""Convert HI-Small_Trans.csv to Parquet with DuckDB.

The CSV is never loaded into pandas. tx_id is the 1-based row number in the
original file (header excluded). The file is not sorted by time, so tx_id is an
identifier, not a time order.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

# The header has two columns named "Account"; names are given explicitly.
CSV_COLUMNS = {
    "ts_raw": "VARCHAR",
    "from_bank_raw": "VARCHAR",
    "from_account": "VARCHAR",
    "to_bank_raw": "VARCHAR",
    "to_account": "VARCHAR",
    "amount_received": "DECIMAL(24,6)",
    "currency_received": "VARCHAR",
    "amount_paid": "DECIMAL(24,6)",
    "currency_paid": "VARCHAR",
    "payment_format": "VARCHAR",
    "is_laundering": "TINYINT",
}

ROW_GROUP_SIZE = 122_880


def _columns_sql() -> str:
    return "{" + ", ".join(f"'{k}': '{v}'" for k, v in CSV_COLUMNS.items()) + "}"


def convert_transactions(csv_path: Path, out_path: Path) -> int:
    """Write transactions.parquet and return its row count."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    # One thread and insertion order preserved: row_number() equals the file row,
    # and the output bytes are stable across runs.
    con.execute("SET threads = 1")
    con.execute("SET enable_progress_bar = false")
    con.execute("SET preserve_insertion_order = true")
    con.execute(
        f"""
        CREATE TABLE raw AS
        SELECT row_number() OVER () AS tx_id, *
        FROM read_csv(?, header = true, parallel = false, auto_detect = false,
                      columns = {_columns_sql()})
        """,
        [str(csv_path)],
    )
    con.execute(
        f"""
        COPY (
            SELECT
                tx_id::BIGINT AS tx_id,
                strptime(ts_raw, '%Y/%m/%d %H:%M') AS ts,
                from_bank_raw,
                from_bank_raw::INTEGER AS from_bank,
                from_account,
                to_bank_raw,
                to_bank_raw::INTEGER AS to_bank,
                to_account,
                amount_received,
                currency_received,
                amount_paid,
                currency_paid,
                payment_format,
                is_laundering = 1 AS is_laundering,
                (from_bank_raw::INTEGER = to_bank_raw::INTEGER
                    AND from_account = to_account) AS is_self_transfer
            FROM raw
            ORDER BY tx_id
        ) TO '{out_path.as_posix()}'
        (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE {ROW_GROUP_SIZE})
        """
    )
    (count,) = con.execute(f"SELECT count(*) FROM '{out_path.as_posix()}'").fetchone()
    con.close()
    return count
