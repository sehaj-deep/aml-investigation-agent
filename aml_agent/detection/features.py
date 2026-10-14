"""Account features for a review period, computed for every account in one pass.

Builds on the risk-rule signals (aml_agent/analysis/population.py) and adds graph,
amount, timing and counterparty features, from non-self transfers. Nothing looks past
the end of the period. Amounts are never added across currencies (they enter only as
per-currency standard scores of their logarithm). Labels are never read.
"""

from __future__ import annotations

from datetime import datetime

import duckdb

from aml_agent.analysis.population import score_population

FEATURES: tuple[str, ...] = (
    # risk-rule signals
    "n_transfers",
    "n_in",
    "n_out",
    "n_cp",
    "receives_and_pays",
    "currency_switch",
    "new_counterparty_share",
    "one_time_counterparty_share",
    "period_activity_share",
    "onward_within_24h_share",
    "rule_score",
    "top_counterparty_score",
    # graph shape
    "senders",
    "receivers",
    "one_off_senders",
    "one_off_receivers",
    "reciprocal_counterparties",
    "currencies_in",
    "currencies_out",
    # amounts (per-currency standard score of log amount)
    "amount_z_mean",
    "amount_z_max",
    "amount_z_min",
    "amount_z_std",
    # timing
    "active_hours_span",
    "transfers_per_active_day",
    "median_hours_to_onward",
    # counterparties
    "cp_rule_score_mean",
    "cp_rule_score_max",
    "cp_currency_switch_count",
    "cp_degree_max",
    "cp_one_time_share_mean",
)


def build_currency_stats(con: duckdb.DuckDBPyConnection, start: datetime, end: datetime) -> None:
    """Mean and spread of log amounts per currency over [start, end] (training data only)."""
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE currency_stats AS
        SELECT currency, avg(ln(amount)) AS mu, stddev_pop(ln(amount)) AS sigma FROM (
            SELECT currency_paid AS currency, amount_paid AS amount FROM transactions
            WHERE NOT is_self_transfer AND ts BETWEEN $p0 AND $pe AND amount_paid > 0
            UNION ALL
            SELECT currency_received, amount_received FROM transactions
            WHERE NOT is_self_transfer AND ts BETWEEN $p0 AND $pe AND amount_received > 0)
        GROUP BY currency
        """,
        {"p0": start, "pe": end},
    )


def build_features(con: duckdb.DuckDBPyConnection, start: datetime, end: datetime) -> None:
    """Create the temp table `features` (b, a, FEATURES...) for the review period.

    Needs `currency_stats` (build_currency_stats) and a `transactions` relation.
    """
    score_population(con, start, end, history_end=end)
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE legs_amount AS
        SELECT from_bank AS b, from_account AS a, to_bank AS cb, to_account AS ca, ts,
               'out' AS dir, currency_paid AS ccy, amount_paid AS amount
        FROM transactions WHERE NOT is_self_transfer AND ts BETWEEN $start AND $end
        UNION ALL
        SELECT to_bank, to_account, from_bank, from_account, ts, 'in', currency_received,
               amount_received
        FROM transactions WHERE NOT is_self_transfer AND ts BETWEEN $start AND $end
        """,
        {"start": start, "end": end},
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE features AS
        WITH shape AS (
            SELECT b, a,
                   count(DISTINCT (cb, ca)) FILTER (WHERE dir = 'in') AS senders,
                   count(DISTINCT (cb, ca)) FILTER (WHERE dir = 'out') AS receivers,
                   count(DISTINCT ccy) FILTER (WHERE dir = 'in') AS currencies_in,
                   count(DISTINCT ccy) FILTER (WHERE dir = 'out') AS currencies_out,
                   date_diff('minute', min(ts), max(ts)) / 60.0 AS active_hours_span,
                   count(*) / greatest(count(DISTINCT ts::DATE), 1) AS transfers_per_active_day
            FROM legs_amount GROUP BY ALL
        ),
        one_off AS (
            SELECT b, a,
                   count(*) FILTER (WHERE n <= 2 AND has_in) AS one_off_senders,
                   count(*) FILTER (WHERE n <= 2 AND has_out) AS one_off_receivers
            FROM (
                SELECT b, a, cb, ca, count(*) AS n, bool_or(dir = 'in') AS has_in,
                       bool_or(dir = 'out') AS has_out
                FROM legs GROUP BY ALL)
            GROUP BY ALL
        ),
        recip AS (
            SELECT b, a, count(*) AS reciprocal_counterparties FROM (
                SELECT b, a, cb, ca FROM legs_amount GROUP BY ALL
                HAVING bool_or(dir = 'in') AND bool_or(dir = 'out'))
            GROUP BY ALL
        ),
        amounts AS (
            SELECT l.b, l.a,
                   avg((ln(l.amount) - s.mu) / nullif(s.sigma, 0)) AS amount_z_mean,
                   max((ln(l.amount) - s.mu) / nullif(s.sigma, 0)) AS amount_z_max,
                   min((ln(l.amount) - s.mu) / nullif(s.sigma, 0)) AS amount_z_min,
                   stddev_pop((ln(l.amount) - s.mu) / nullif(s.sigma, 0)) AS amount_z_std
            FROM legs_amount l JOIN currency_stats s ON s.currency = l.ccy
            WHERE l.amount > 0 GROUP BY ALL
        ),
        hold AS (
            SELECT i.b, i.a,
                   median(date_diff('minute', i.ts, o.ts) / 60.0) AS median_hours_to_onward
            FROM (SELECT b, a, ts FROM legs WHERE dir = 'in') i
            ASOF JOIN (SELECT b, a, ts FROM legs WHERE dir = 'out') o
              ON i.b = o.b AND i.a = o.a AND o.ts >= i.ts
            GROUP BY ALL
        ),
        neighbors AS (
            SELECT p.b, p.a,
                   avg(s.score) AS cp_rule_score_mean,
                   max(s.score) AS cp_rule_score_max,
                   count(*) FILTER (WHERE s.currency_switch) AS cp_currency_switch_count,
                   max(s.n_cp) AS cp_degree_max,
                   avg(s.one_time_counterparty_share) AS cp_one_time_share_mean
            FROM pairs p JOIN account_scores s ON s.b = p.cb AND s.a = p.ca
            GROUP BY ALL
        )
        SELECT r.b, r.a,
               r.n_transfers, r.n_in, r.n_out, r.n_cp,
               r.receives_and_pays::INTEGER AS receives_and_pays,
               r.currency_switch::INTEGER AS currency_switch,
               r.new_counterparty_share, r.one_time_counterparty_share,
               r.period_activity_share, r.onward_within_24h_share,
               r.score AS rule_score, r.top_counterparty_score,
               shape.senders, shape.receivers,
               COALESCE(one_off.one_off_senders, 0) AS one_off_senders,
               COALESCE(one_off.one_off_receivers, 0) AS one_off_receivers,
               COALESCE(recip.reciprocal_counterparties, 0) AS reciprocal_counterparties,
               shape.currencies_in, shape.currencies_out,
               amounts.amount_z_mean, amounts.amount_z_max, amounts.amount_z_min,
               amounts.amount_z_std,
               shape.active_hours_span, shape.transfers_per_active_day,
               hold.median_hours_to_onward,
               neighbors.cp_rule_score_mean, neighbors.cp_rule_score_max,
               neighbors.cp_currency_switch_count, neighbors.cp_degree_max,
               neighbors.cp_one_time_share_mean
        FROM account_risk r
        JOIN shape USING (b, a)
        LEFT JOIN one_off USING (b, a)
        LEFT JOIN recip USING (b, a)
        LEFT JOIN amounts USING (b, a)
        LEFT JOIN hold USING (b, a)
        LEFT JOIN neighbors USING (b, a)
        """
    )
