"""The real tool DB exposes no labels, and tool results match the Parquet source."""

import duckdb
import pytest

from aml_agent.alerts.io import read_alerts
from aml_agent.data.tooldb import tool_db_path
from aml_agent.tools.graph import GraphTools

pytestmark = pytest.mark.data


@pytest.fixture(scope="module")
def tools():
    if not tool_db_path().exists():
        pytest.skip("tools.duckdb missing; run the conversion")
    t = GraphTools()
    yield t
    t.close()


def test_tool_db_has_no_labels_or_ground_truth(tools):
    tables = {r[0] for r in tools.con.execute("SHOW TABLES").fetchall()}
    assert tables == {"transactions", "banks"}
    cols = {r[0] for r in tools.con.execute("DESCRIBE transactions").fetchall()}
    assert "is_laundering" not in cols


def test_tool_db_opened_read_only(tools):
    with pytest.raises(duckdb.Error):
        tools.con.execute("UPDATE transactions SET amount_paid = 0 WHERE tx_id = 1")


@pytest.mark.parametrize("alert", read_alerts("dev")[:6], ids=lambda a: a.alert_id)
def test_neighbors_match_parquet(tools, con, alert):
    out = tools.get_neighbors(
        bank_id=alert.seed_bank,
        account=alert.seed_account,
        window_start=alert.window_start,
        window_end=alert.window_end,
        direction="out",
        limit=100,
    )
    expected = con.execute(
        """
        SELECT to_bank, to_account, count(*) FROM transactions
        WHERE from_bank = ? AND from_account = ? AND NOT is_self_transfer
          AND ts BETWEEN ? AND ?
        GROUP BY 1, 2
        """,
        [alert.seed_bank, alert.seed_account, alert.window_start, alert.window_end],
    ).fetchall()
    got = {(c["bank_id"], c["account"], c["n_tx"]) for c in out["counterparties"]}
    assert got == set(expected)
