"""Score every account in a review period with the risk rules, in one set-based pass.

Used for the detection part of the scorecard (docs/SCORECARD.md, part A): the case
file scores one subject at a time through the `get_account_behavior` tool; this module
computes the same signals for all accounts at once in DuckDB, so detection can be
measured at the data's natural laundering rate. `tests/golden/test_population.py`
checks that both give identical signals.

Definitions match `GraphTools.get_account_behavior` and `analysis/risk.py`:
non-self transfers only; the review period is [start, end]; "before" means from the
start of the data to the start of the period; activity share is relative to the whole
data the tools show. The case score adds the highest score among up to 8 first-time
counterparties (pairs with at most 2 transfers in the period), ordered by transfer
count, bank and account. (The case file takes those from the subject's top 100
counterparties, which only differs for accounts with more than 100.)
"""

from __future__ import annotations

from datetime import datetime

import duckdb

from aml_agent.analysis import risk
from aml_agent.tools.graph import data_end

DATA_START = datetime(2022, 9, 1)
PRIMARY_END = datetime(2022, 9, 10, 23, 59)


def score_population(
    con: duckdb.DuckDBPyConnection,
    start: datetime,
    end: datetime,
    history_end: datetime | None = None,
) -> None:
    """Create the temp table `account_risk` for the review period [start, end].

    `con` needs a `transactions` relation with the tool columns. Activity share is
    relative to the account's activity from the start of the data to `history_end`
    (by default the end of the data the tools show, as the tool does; detection passes
    `end`, so no feature looks past the period).
    """
    period = {"start": start, "end": end}
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE legs AS
        SELECT from_bank AS b, from_account AS a, to_bank AS cb, to_account AS ca, ts,
               'out' AS dir, currency_paid AS ccy
        FROM transactions WHERE NOT is_self_transfer AND ts BETWEEN $start AND $end
        UNION ALL
        SELECT to_bank, to_account, from_bank, from_account, ts, 'in', currency_received
        FROM transactions WHERE NOT is_self_transfer AND ts BETWEEN $start AND $end
        """,
        period,
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE pairs AS
        SELECT b, a, cb, ca, count(*) AS n FROM legs GROUP BY ALL
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE before_pairs AS
        SELECT DISTINCT from_bank AS b, from_account AS a, to_bank AS cb, to_account AS ca
        FROM transactions WHERE NOT is_self_transfer AND ts >= $p0 AND ts < $start
        UNION
        SELECT DISTINCT to_bank, to_account, from_bank, from_account
        FROM transactions WHERE NOT is_self_transfer AND ts >= $p0 AND ts < $start
        """,
        {"p0": DATA_START, "start": start},
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE totals AS
        SELECT b, a, count(*) AS total FROM (
            SELECT from_bank AS b, from_account AS a FROM transactions
            WHERE NOT is_self_transfer AND ts BETWEEN $p0 AND $pe
            UNION ALL
            SELECT to_bank, to_account FROM transactions
            WHERE NOT is_self_transfer AND ts BETWEEN $p0 AND $pe)
        GROUP BY ALL
        """,
        {"p0": DATA_START, "pe": history_end or data_end()},
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE onward AS
        WITH ins AS (SELECT b, a, ts FROM legs WHERE dir = 'in'),
             outs AS (SELECT b, a, ts FROM legs WHERE dir = 'out')
        SELECT i.b, i.a,
               avg(CASE WHEN o.ts IS NOT NULL AND o.ts - i.ts <= INTERVAL 24 HOUR
                        THEN 1.0 ELSE 0.0 END) AS share
        FROM ins i ASOF LEFT JOIN outs o ON i.b = o.b AND i.a = o.a AND o.ts >= i.ts
        GROUP BY ALL
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE account_signals AS
        WITH base AS (
            SELECT b, a, count(*) AS n_transfers,
                   count(*) FILTER (WHERE dir = 'in') AS n_in,
                   count(*) FILTER (WHERE dir = 'out') AS n_out
            FROM legs GROUP BY ALL
        ),
        cp AS (
            SELECT p.b, p.a, count(*) AS n_cp,
                   avg(CASE WHEN p.n <= {risk.ONE_TIME_MAX_TRANSFERS} THEN 1.0 ELSE 0.0 END)
                       AS one_time_share,
                   avg(CASE WHEN bp.b IS NULL THEN 1.0 ELSE 0.0 END) AS new_share
            FROM pairs p
            LEFT JOIN before_pairs bp
              ON bp.b = p.b AND bp.a = p.a AND bp.cb = p.cb AND bp.ca = p.ca
            GROUP BY ALL
        ),
        ccy AS (
            SELECT b, a, count(*) FILTER (WHERE has_in AND has_out) AS overlap
            FROM (
                SELECT b, a, ccy, bool_or(dir = 'in') AS has_in, bool_or(dir = 'out') AS has_out
                FROM legs GROUP BY ALL)
            GROUP BY ALL
        )
        SELECT base.b, base.a, base.n_transfers, base.n_in, base.n_out, cp.n_cp,
               base.n_in > 0 AND base.n_out > 0 AS receives_and_pays,
               base.n_in > 0 AND base.n_out > 0 AND ccy.overlap = 0 AS currency_switch,
               cp.new_share AS new_counterparty_share,
               cp.one_time_share AS one_time_counterparty_share,
               base.n_transfers / totals.total AS period_activity_share,
               COALESCE(onward.share, 0.0) AS onward_within_24h_share
        FROM base
        JOIN cp USING (b, a)
        JOIN ccy USING (b, a)
        JOIN totals USING (b, a)
        LEFT JOIN onward USING (b, a)
        """
    )
    w = {r.code: r.weight for r in risk.RULES}
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE account_scores AS
        SELECT *,
            (CASE WHEN currency_switch THEN {w["R1"]} ELSE 0 END
             + CASE WHEN receives_and_pays THEN {w["R2"]} ELSE 0 END
             + CASE WHEN new_counterparty_share >= {risk.NEW_COUNTERPARTY_MIN}
                    THEN {w["R3"]} ELSE 0 END
             + CASE WHEN one_time_counterparty_share >= {risk.ONE_TIME_COUNTERPARTY_MIN}
                    THEN {w["R4"]} ELSE 0 END
             + CASE WHEN period_activity_share >= {risk.PERIOD_ACTIVITY_MIN}
                    THEN {w["R5"]} ELSE 0 END
             + CASE WHEN onward_within_24h_share >= {risk.ONWARD_24H_MIN}
                    THEN {w["R6"]} ELSE 0 END) AS score
        FROM account_signals
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE account_risk AS
        WITH first_time AS (
            SELECT p.b, p.a, p.cb, p.ca,
                   row_number() OVER (PARTITION BY p.b, p.a ORDER BY p.n, p.cb, p.ca) AS rk
            FROM pairs p WHERE p.n <= {risk.ONE_TIME_MAX_TRANSFERS}
        ),
        top_cp AS (
            SELECT f.b, f.a, max(s.score) AS top_score
            FROM first_time f
            JOIN account_scores s ON s.b = f.cb AND s.a = f.ca
            WHERE f.rk <= {risk.MAX_RISK_COUNTERPARTIES}
            GROUP BY ALL
        )
        SELECT s.*, COALESCE(t.top_score, 0) AS top_counterparty_score,
               s.score + COALESCE(t.top_score, 0) AS case_score
        FROM account_scores s LEFT JOIN top_cp t USING (b, a)
        """
    )
