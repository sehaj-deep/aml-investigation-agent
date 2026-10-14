"""Transaction features: the transfer itself, its payment, and both accounts.

A bank's transaction monitoring scores each payment, and an alert is the account
behind the suspicious payments. Each transaction gets:
- its own features (amount for its currency, currency change, timing, how the two
  accounts have dealt with each other before);
- payment format, as an analyst sees it (left out for the "without format" model);
- the sender's and the receiver's account features for the review period
  (aml_agent/detection/features.py), prefixed `s_` and `r_`.

Nothing looks past the end of the review period, and labels are never read.
"""

from __future__ import annotations

from datetime import datetime

import duckdb

from aml_agent.detection.features import FEATURES, build_features

PAYMENT_FORMATS = ("ACH", "Bitcoin", "Cash", "Cheque", "Credit Card", "Reinvestment", "Wire")

TX_FEATURES: tuple[str, ...] = (
    "amount_z",
    "cross_currency",
    "same_bank",
    "self_transfer",
    "hour",
    "pair_prior_count",
    "pair_reverse_prior_count",
    "pair_period_count",
    "hours_since_sender_received",
    "hours_to_receiver_pays",
)
FORMAT_FEATURES: tuple[str, ...] = (
    *(f"format_{f.lower().replace(' ', '_')}" for f in PAYMENT_FORMATS),
    "sender_format_share",
    "receiver_format_share",
)
ACCOUNT_FEATURES: tuple[str, ...] = (
    *(f"s_{f}" for f in FEATURES),
    *(f"r_{f}" for f in FEATURES),
)


def feature_names(with_format: bool) -> tuple[str, ...]:
    return (*TX_FEATURES, *(FORMAT_FEATURES if with_format else ()), *ACCOUNT_FEATURES)


def build_history(con: duckdb.DuckDBPyConnection) -> None:
    """Per-transaction history from the start of the data (earlier rows only).

    Creates `tx_history(tx_id, pair_prior_count, pair_reverse_prior_count,
    hours_since_sender_received)`. Same-minute rows are ordered by tx_id.
    """
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE pair_seq AS
        SELECT tx_id, ts, from_bank, from_account, to_bank, to_account,
               row_number() OVER (PARTITION BY from_bank, from_account, to_bank, to_account
                                  ORDER BY ts, tx_id) AS seq
        FROM transactions WHERE NOT is_self_transfer
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE tx_history AS
        WITH received AS (
            SELECT to_bank AS b, to_account AS a, ts FROM transactions
            WHERE NOT is_self_transfer
        )
        SELECT t.tx_id,
               COALESCE(p.seq - 1, 0) AS pair_prior_count,
               COALESCE(r.seq, 0) AS pair_reverse_prior_count,
               date_diff('minute', i.ts, t.ts) / 60.0 AS hours_since_sender_received
        FROM transactions t
        LEFT JOIN pair_seq p USING (tx_id)
        ASOF LEFT JOIN pair_seq r
          ON r.from_bank = t.to_bank AND r.from_account = t.to_account
         AND r.to_bank = t.from_bank AND r.to_account = t.from_account AND r.ts < t.ts
        ASOF LEFT JOIN received i
          ON i.b = t.from_bank AND i.a = t.from_account AND i.ts <= t.ts
        """
    )


def build_transaction_features(
    con: duckdb.DuckDBPyConnection, start: datetime, end: datetime
) -> None:
    """Create `tx_features` (tx_id, ts, sender, receiver, every feature) for [start, end].

    Needs `currency_stats` and `tx_history`.
    """
    build_features(con, start, end)
    period = {"start": start, "end": end}
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE format_mix AS
        SELECT b, a, dir, fmt, count(*) / sum(count(*)) OVER (PARTITION BY b, a, dir) AS share
        FROM (
            SELECT from_bank AS b, from_account AS a, 'out' AS dir, payment_format AS fmt
            FROM transactions WHERE ts BETWEEN $start AND $end
            UNION ALL
            SELECT to_bank, to_account, 'in', payment_format
            FROM transactions WHERE ts BETWEEN $start AND $end)
        GROUP BY b, a, dir, fmt
        """,
        period,
    )
    formats = ",\n".join(
        f"(t.payment_format = '{f}')::INTEGER AS format_{f.lower().replace(' ', '_')}"
        for f in PAYMENT_FORMATS
    )
    accounts = ",\n".join(
        [f"s.{f} AS s_{f}" for f in FEATURES] + [f"r.{f} AS r_{f}" for f in FEATURES]
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE tx_features AS
        WITH tx AS (
            SELECT * FROM transactions WHERE ts BETWEEN $start AND $end
        ),
        period_pairs AS (
            SELECT from_bank, from_account, to_bank, to_account, count(*) AS n
            FROM tx WHERE NOT is_self_transfer GROUP BY ALL
        ),
        pays AS (
            SELECT from_bank AS b, from_account AS a, ts FROM tx WHERE NOT is_self_transfer
        )
        SELECT t.tx_id, t.ts, t.from_bank, t.from_account, t.to_bank, t.to_account,
               (ln(t.amount_paid) - c.mu) / nullif(c.sigma, 0) AS amount_z,
               (t.currency_paid <> t.currency_received)::INTEGER AS cross_currency,
               (t.from_bank = t.to_bank)::INTEGER AS same_bank,
               t.is_self_transfer::INTEGER AS self_transfer,
               hour(t.ts) AS hour,
               h.pair_prior_count, h.pair_reverse_prior_count,
               COALESCE(pp.n, 0) AS pair_period_count,
               h.hours_since_sender_received,
               date_diff('minute', t.ts, o.ts) / 60.0 AS hours_to_receiver_pays,
               {formats},
               fs.share AS sender_format_share,
               fr.share AS receiver_format_share,
               {accounts}
        FROM tx t
        JOIN tx_history h USING (tx_id)
        LEFT JOIN currency_stats c ON c.currency = t.currency_paid AND t.amount_paid > 0
        LEFT JOIN period_pairs pp
          ON pp.from_bank = t.from_bank AND pp.from_account = t.from_account
         AND pp.to_bank = t.to_bank AND pp.to_account = t.to_account
        ASOF LEFT JOIN pays o ON o.b = t.to_bank AND o.a = t.to_account AND o.ts >= t.ts
        LEFT JOIN format_mix fs ON fs.b = t.from_bank AND fs.a = t.from_account
         AND fs.dir = 'out' AND fs.fmt = t.payment_format
        LEFT JOIN format_mix fr ON fr.b = t.to_bank AND fr.a = t.to_account
         AND fr.dir = 'in' AND fr.fmt = t.payment_format
        LEFT JOIN features s ON s.b = t.from_bank AND s.a = t.from_account
        LEFT JOIN features r ON r.b = t.to_bank AND r.a = t.to_account
        """,
        period,
    )
