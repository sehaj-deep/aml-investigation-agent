from __future__ import annotations

import duckdb
import pytest

from aml_agent.data.views import connect


@pytest.fixture(scope="session")
def con() -> duckdb.DuckDBPyConnection:
    """Views over the converted Parquet tables. Skips if they are missing."""
    try:
        c = connect()
    except FileNotFoundError as exc:
        pytest.skip(str(exc))
    yield c
    c.close()


def scalar(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None):
    return con.execute(sql, params or []).fetchone()[0]
