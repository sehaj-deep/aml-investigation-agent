"""Build every Parquet table from the three raw HI-Small files.

Output (all under PARQUET_DIR, gitignored):
    transactions, accounts, banks, pattern_blocks, pattern_transactions,
    other_laundering, pattern_accounts, seed_eligible, and MANIFEST.json with
    sha256 checksums of the sources and outputs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from aml_agent import config
from aml_agent.data.accounts import build_accounts
from aml_agent.data.convert import ROW_GROUP_SIZE, convert_transactions
from aml_agent.data.derived import build_derived
from aml_agent.data.patterns import build_pattern_tables, parse_patterns
from aml_agent.data.tooldb import build_tool_db

DERIVED_TABLES = [
    "accounts",
    "banks",
    "pattern_blocks",
    "pattern_transactions",
    "other_laundering",
    "pattern_accounts",
    "seed_eligible",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_all(data_dir: Path | None = None, out_dir: Path | None = None) -> dict:
    data_dir = data_dir or config.data_dir()
    out_dir = out_dir or config.parquet_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    trans_csv = data_dir / config.TRANS_FILE
    accounts_csv = data_dir / config.ACCOUNTS_FILE
    patterns_txt = data_dir / config.PATTERNS_FILE

    tx_path = out_dir / "transactions.parquet"
    n_tx = convert_transactions(trans_csv, tx_path)

    con = duckdb.connect()
    con.execute("SET threads = 1")
    con.execute("SET preserve_insertion_order = true")
    con.execute(f"CREATE VIEW transactions AS SELECT * FROM '{tx_path.as_posix()}'")
    build_accounts(con, accounts_csv)
    build_pattern_tables(con, parse_patterns(patterns_txt))
    build_derived(con)
    for table in DERIVED_TABLES:
        target = (out_dir / f"{table}.parquet").as_posix()
        con.execute(
            f"COPY (SELECT * FROM {table}) TO '{target}' "
            f"(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE {ROW_GROUP_SIZE})"
        )
    con.close()

    manifest = {
        "duckdb_version": duckdb.__version__,
        "sources": {p.name: sha256(p) for p in (trans_csv, accounts_csv, patterns_txt)},
        "outputs": {
            f"{name}.parquet": sha256(out_dir / f"{name}.parquet")
            for name in ["transactions", *DERIVED_TABLES]
        },
        "transactions_rows": n_tx,
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # The read-only database the graph tools open (no labels). Not in the manifest:
    # DuckDB files are not byte-stable; it is derived from the checksummed Parquet.
    build_tool_db(out_dir)
    return manifest
