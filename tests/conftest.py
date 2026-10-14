from __future__ import annotations

import duckdb
import pytest

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


@pytest.fixture(scope="session")
def con() -> duckdb.DuckDBPyConnection:
    """Read-only views over the converted Parquet tables. Skips if they are missing."""
    missing = [t for t in TABLES if not config.table_path(t).exists()]
    if missing:
        pytest.skip(f"Parquet tables missing ({', '.join(missing)}); run the conversion first")
    c = duckdb.connect()
    for t in TABLES:
        c.execute(f"CREATE VIEW {t} AS SELECT * FROM '{config.table_path(t).as_posix()}'")
    yield c
    c.close()


def scalar(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None):
    return con.execute(sql, params or []).fetchone()[0]
