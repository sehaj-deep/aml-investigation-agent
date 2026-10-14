"""Open a DuckDB connection with read-only views over the Parquet tables."""

from __future__ import annotations

import duckdb

from aml_agent import config

TABLES = [
    "transactions",
    "accounts",
    "banks",
    "pattern_blocks",
    "pattern_transactions",
    "other_laundering",
    "pattern_accounts",
    "seed_eligible",
]


def connect(tables: list[str] | None = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    for t in tables or TABLES:
        path = config.table_path(t)
        if not path.exists():
            raise FileNotFoundError(f"{path} missing; run scripts/convert_to_parquet.py")
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM '{path.as_posix()}'")
    return con
