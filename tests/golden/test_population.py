"""The set-based population scorer gives the same signals and scores as the
per-account tool (real data, a seeded sample of accounts)."""

from datetime import datetime

import duckdb
import pytest

from aml_agent.analysis.population import score_population
from aml_agent.data.tooldb import tool_db_path
from aml_agent.tools.graph import GraphTools

pytestmark = pytest.mark.data

START, END = datetime(2022, 9, 7), datetime(2022, 9, 9, 23, 59)


@pytest.fixture(scope="module")
def scored():
    if not tool_db_path().exists():
        pytest.skip("tools.duckdb missing; run the conversion")
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    con.execute(f"ATTACH '{tool_db_path().as_posix()}' AS src (READ_ONLY)")
    con.execute("CREATE VIEW transactions AS SELECT * FROM src.transactions")
    score_population(con, START, END)
    yield con
    con.close()


def test_population_matches_the_tool(scored):
    rows = scored.execute(
        """
        SELECT b, a, n_transfers, receives_and_pays, currency_switch, new_counterparty_share,
               one_time_counterparty_share, period_activity_share, onward_within_24h_share, score
        FROM account_risk USING SAMPLE reservoir(150 ROWS) REPEATABLE (11)
        """
    ).fetchall()
    tools = GraphTools()
    mismatches = []
    for r in rows:
        out = tools.get_account_behavior(
            bank_id=r[0], account=r[1], window_start=START, window_end=END
        )
        s = out["signals"]
        population = (r[2], r[3], r[4], *(round(x, 4) for x in r[5:9]), r[9])
        tool = (
            s["n_transfers"],
            s["receives_and_pays"],
            s["currency_switch"],
            s["new_counterparty_share"],
            s["one_time_counterparty_share"],
            s["period_activity_share"],
            s["onward_within_24h_share"],
            out["score"],
        )
        if population != tool:
            mismatches.append((r[0], r[1], population, tool))
    tools.close()
    assert mismatches == []


def test_case_score_adds_the_riskiest_first_time_counterparty(scored):
    bad = scored.execute(
        "SELECT count(*) FROM account_risk WHERE case_score <> score + top_counterparty_score"
    ).fetchone()[0]
    assert bad == 0
