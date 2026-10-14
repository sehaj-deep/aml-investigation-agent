"""Parse HI-Small_Patterns.txt and match each pattern row to exactly one tx_id.

Each block looks like:
    BEGIN LAUNDERING ATTEMPT - FAN-OUT:  Max 16-degree Fan-Out
    <transaction rows, same format as the transactions CSV>
    END LAUNDERING ATTEMPT - FAN-OUT
Blocks are numbered 1..N in file order (block_id).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

BEGIN_RE = re.compile(r"^BEGIN LAUNDERING ATTEMPT - ([A-Z-]+)(?::\s*(.*))?$")
DEGREE_RE = re.compile(r"Max (\d+)-degree")
HOPS_RE = re.compile(r"Max (\d+) hops")


@dataclass
class PatternBlock:
    block_id: int
    pattern_type: str
    header_param: str | None
    param_name: str | None
    param_value: int | None
    rows: list[list[str]] = field(default_factory=list)


def parse_param(text: str | None) -> tuple[str | None, int | None]:
    """Turn a header parameter like 'Max 16-degree Fan-Out' into ('degree', 16)."""
    if not text:
        return None, None
    if m := DEGREE_RE.search(text):
        return "degree", int(m.group(1))
    if m := HOPS_RE.search(text):
        return "hops", int(m.group(1))
    raise ValueError(f"unknown pattern header parameter: {text!r}")


def parse_patterns(path: Path) -> list[PatternBlock]:
    blocks: list[PatternBlock] = []
    current: PatternBlock | None = None
    with path.open(newline="", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            if m := BEGIN_RE.match(line):
                if current is not None:
                    raise ValueError(f"line {lineno}: BEGIN inside an open block")
                name, value = parse_param(m.group(2))
                current = PatternBlock(len(blocks) + 1, m.group(1), m.group(2), name, value)
            elif line.startswith("END LAUNDERING ATTEMPT"):
                if current is None:
                    raise ValueError(f"line {lineno}: END without BEGIN")
                blocks.append(current)
                current = None
            else:
                if current is None:
                    raise ValueError(f"line {lineno}: row outside a block")
                row = next(csv.reader([line]))
                if len(row) != 11:
                    raise ValueError(f"line {lineno}: expected 11 fields, got {len(row)}")
                current.rows.append(row)
    if current is not None:
        raise ValueError("file ended inside a block")
    return blocks


def build_pattern_tables(con: duckdb.DuckDBPyConnection, blocks: list[PatternBlock]) -> None:
    """Create pattern_blocks and pattern_transactions. Needs a `transactions` table or view."""
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE pattern_rows_raw (
            block_id INTEGER, row_in_block INTEGER, ts_raw VARCHAR,
            from_bank_raw VARCHAR, from_account VARCHAR, to_bank_raw VARCHAR,
            to_account VARCHAR, amount_received VARCHAR, currency_received VARCHAR,
            amount_paid VARCHAR, currency_paid VARCHAR, payment_format VARCHAR,
            is_laundering VARCHAR)
        """
    )
    con.executemany(
        "INSERT INTO pattern_rows_raw VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [[b.block_id, i, *row] for b in blocks for i, row in enumerate(b.rows, start=1)],
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE pattern_transactions AS
        SELECT p.block_id, p.row_in_block, t.tx_id
        FROM pattern_rows_raw p
        JOIN transactions t
          ON t.ts = strptime(p.ts_raw, '%Y/%m/%d %H:%M')
         AND t.from_bank = p.from_bank_raw::INTEGER
         AND t.from_account = p.from_account
         AND t.to_bank = p.to_bank_raw::INTEGER
         AND t.to_account = p.to_account
         AND t.amount_received = p.amount_received::DECIMAL(24,6)
         AND t.currency_received = p.currency_received
         AND t.amount_paid = p.amount_paid::DECIMAL(24,6)
         AND t.currency_paid = p.currency_paid
         AND t.payment_format = p.payment_format
         AND t.is_laundering = (p.is_laundering = '1')
        ORDER BY p.block_id, p.row_in_block
        """
    )
    bad = con.execute(
        """
        SELECT count(*) FROM (
            SELECT p.block_id, p.row_in_block, count(pt.tx_id) AS n
            FROM pattern_rows_raw p
            LEFT JOIN pattern_transactions pt USING (block_id, row_in_block)
            GROUP BY p.block_id, p.row_in_block
            HAVING count(pt.tx_id) <> 1)
        """
    ).fetchone()[0]
    if bad:
        raise ValueError(f"{bad} pattern rows did not match exactly one transaction")
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE block_meta (
            block_id INTEGER, pattern_type VARCHAR, header_param VARCHAR,
            param_name VARCHAR, param_value INTEGER)
        """
    )
    con.executemany(
        "INSERT INTO block_meta VALUES (?, ?, ?, ?, ?)",
        [[b.block_id, b.pattern_type, b.header_param, b.param_name, b.param_value] for b in blocks],
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE pattern_blocks AS
        SELECT m.block_id, m.pattern_type, m.header_param, m.param_name, m.param_value,
               count(*) AS n_tx, min(t.ts) AS first_ts, max(t.ts) AS last_ts
        FROM block_meta m
        JOIN pattern_transactions pt USING (block_id)
        JOIN transactions t USING (tx_id)
        GROUP BY ALL
        ORDER BY m.block_id
        """
    )
