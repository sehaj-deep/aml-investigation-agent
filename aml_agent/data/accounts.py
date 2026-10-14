"""Load HI-Small_accounts.csv into the accounts and banks tables.

Bank IDs are read as strings and normalized to integers, because the
transactions file pads them differently. Accounts are keyed by
(integer bank ID, account number): 8 account numbers exist at two banks.
Bank names are labels only; many bank IDs share one name.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from aml_agent.data.jurisdictions import US_STYLE_LABEL, jurisdiction_sql_case

LABEL_REGEX = "^(.*) Bank #[0-9]+$"


def build_accounts(con: duckdb.DuckDBPyConnection, csv_path: Path) -> None:
    """Create the `accounts` and `banks` tables in `con`."""
    con.execute(
        """
        CREATE OR REPLACE TABLE accounts AS
        SELECT
            "Bank ID"::INTEGER AS bank_id,
            "Bank ID" AS bank_id_raw,
            "Account Number" AS account,
            "Bank Name" AS bank_name,
            "Entity ID" AS entity_id,
            "Entity Name" AS entity_name
        FROM read_csv(?, header = true, all_varchar = true)
        ORDER BY bank_id, account
        """,
        [str(csv_path)],
    )
    names_per_bank = con.execute(
        "SELECT max(n) FROM (SELECT count(DISTINCT bank_name) AS n FROM accounts GROUP BY bank_id)"
    ).fetchone()[0]
    if names_per_bank != 1:
        raise ValueError("a bank ID has more than one name")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE banks AS
        WITH named AS (
            SELECT bank_id, any_value(bank_name) AS bank_name
            FROM accounts GROUP BY bank_id
        ),
        labeled AS (
            SELECT bank_id, bank_name,
                   CASE WHEN regexp_matches(bank_name, '{LABEL_REGEX}')
                        THEN regexp_extract(bank_name, '{LABEL_REGEX}', 1)
                        ELSE '{US_STYLE_LABEL}' END AS bank_label
            FROM named
        )
        SELECT bank_id, bank_name, bank_label,
               {jurisdiction_sql_case("bank_label")} AS jurisdiction
        FROM labeled
        ORDER BY bank_id
        """
    )
    unmapped = con.execute("SELECT count(*) FROM banks WHERE jurisdiction IS NULL").fetchone()[0]
    if unmapped:
        raise ValueError(f"{unmapped} banks have a label with no jurisdiction mapping")
