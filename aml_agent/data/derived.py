"""Derived tables: other_laundering, pattern_accounts, seed_eligible.

- other_laundering: labeled rows in no pattern block ("Other" laundering). Never
  used as pattern ground truth.
- pattern_accounts: (block_id, bank_id, account) for every party of a block row.
- seed_eligible: accounts of multi-row blocks that appear in exactly one block
  and in no other_laundering row. Only these may seed a positive alert.
"""

from __future__ import annotations

import duckdb


def build_derived(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE OR REPLACE TABLE other_laundering AS
        SELECT t.tx_id FROM transactions t
        WHERE t.is_laundering
          AND t.tx_id NOT IN (SELECT tx_id FROM pattern_transactions)
        ORDER BY t.tx_id
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE pattern_accounts AS
        SELECT DISTINCT block_id, bank_id, account FROM (
            SELECT pt.block_id, t.from_bank AS bank_id, t.from_account AS account
            FROM pattern_transactions pt JOIN transactions t USING (tx_id)
            UNION ALL
            SELECT pt.block_id, t.to_bank, t.to_account
            FROM pattern_transactions pt JOIN transactions t USING (tx_id))
        ORDER BY ALL
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE seed_eligible AS
        WITH other_accounts AS (
            SELECT t.from_bank AS bank_id, t.from_account AS account
            FROM other_laundering o JOIN transactions t USING (tx_id)
            UNION
            SELECT t.to_bank, t.to_account
            FROM other_laundering o JOIN transactions t USING (tx_id)
        ),
        single_block AS (
            SELECT bank_id, account FROM pattern_accounts
            GROUP BY bank_id, account HAVING count(DISTINCT block_id) = 1
        )
        SELECT pa.block_id, pa.bank_id, pa.account
        FROM pattern_accounts pa
        JOIN single_block USING (bank_id, account)
        JOIN pattern_blocks b USING (block_id)
        ANTI JOIN other_accounts oa
          ON oa.bank_id = pa.bank_id AND oa.account = pa.account
        WHERE b.n_tx >= 2
        ORDER BY ALL
        """
    )
