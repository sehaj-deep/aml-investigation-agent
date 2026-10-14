"""Build the DuckDB file the graph tools open read-only.

It holds only what an investigator may see: transactions WITHOUT the
is_laundering label, and banks. No pattern, label or alert tables. The tool
server opens it with read_only=True, so any write fails at the database level.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from aml_agent import config

TOOL_DB_NAME = "tools.duckdb"

# Columns the tools may read. is_laundering is deliberately absent.
TOOL_TRANSACTION_COLUMNS = [
    "tx_id",
    "ts",
    "from_bank",
    "from_account",
    "to_bank",
    "to_account",
    "amount_received",
    "currency_received",
    "amount_paid",
    "currency_paid",
    "payment_format",
    "is_self_transfer",
]


def tool_db_path() -> Path:
    return config.parquet_dir() / TOOL_DB_NAME


def build_tool_db(parquet_dir: Path | None = None, out_path: Path | None = None) -> Path:
    parquet_dir = parquet_dir or config.parquet_dir()
    out_path = out_path or parquet_dir / TOOL_DB_NAME
    out_path.unlink(missing_ok=True)
    con = duckdb.connect(str(out_path))
    con.execute("SET enable_progress_bar = false")
    cols = ", ".join(TOOL_TRANSACTION_COLUMNS)
    con.execute(
        f"CREATE TABLE transactions AS SELECT {cols} "
        f"FROM '{(parquet_dir / 'transactions.parquet').as_posix()}' ORDER BY tx_id"
    )
    con.execute(
        "CREATE TABLE banks AS SELECT bank_id, bank_name, jurisdiction "
        f"FROM '{(parquet_dir / 'banks.parquet').as_posix()}' ORDER BY bank_id"
    )
    con.execute("CHECKPOINT")
    con.close()
    return out_path
