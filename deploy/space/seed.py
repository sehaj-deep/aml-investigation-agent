"""Load the demo database at container start.

Creates every table with the application's own set-up code (store, audit log, LangGraph
checkpoints, guidance, demo limits), then copies in the rows exported by
scripts/build_space.py: the demo alerts, their reviewed cases, decisions, copilot
answers, SAR drafts, audit log, workflow checkpoints and the guidance passages. Serial
counters are moved past the loaded rows so new decisions and answers get fresh ids.
"""

from __future__ import annotations

import asyncio
import csv
import os
import sys
from pathlib import Path

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

from aml_agent import demo, store
from aml_agent.audit import PostgresAudit
from aml_agent.guidance.schema import SCHEMA as GUIDANCE_SCHEMA
from aml_agent.guidance.schema import reader_role

SEED = Path(__file__).resolve().parents[1] / "data" / "seed"
# Parents before children (foreign keys).
TABLES = [
    "alerts",
    "cases",
    "decisions",
    "copilot_messages",
    "sar_drafts",
    "audit_log",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "guidance.passages",
]

csv.field_size_limit(sys.maxsize if sys.maxsize < 2**31 else 2**31 - 1)


async def create_app_tables() -> None:
    async with store.make_pool() as pool:
        await store.init_schema(pool)
        await PostgresAudit(pool).init_schema()
        await demo.init(pool)


def main() -> None:
    url = store.database_url()
    asyncio.run(create_app_tables())
    with PostgresSaver.from_conn_string(url) as saver:
        saver.setup()
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(GUIDANCE_SCHEMA)
        for table in TABLES:
            path = SEED / f"{table}.csv"
            if not path.exists():
                continue
            with path.open(encoding="utf-8", newline="") as f:
                header = next(csv.reader(f))
            columns = ", ".join(f'"{c}"' for c in header)
            with (
                path.open("rb") as f,
                conn.cursor().copy(
                    f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true)"
                ) as copy,
            ):
                while chunk := f.read(1 << 20):
                    copy.write(chunk)
            n = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"seed: {table} {n} rows", flush=True)
        # Serial ids continue after the loaded rows.
        for table, column, seq in conn.execute(
            """
            SELECT table_schema || '.' || table_name, column_name,
                   pg_get_serial_sequence(table_schema || '.' || table_name, column_name)
            FROM information_schema.columns
            WHERE column_default LIKE 'nextval%' AND table_schema IN ('public', 'guidance')
            """
        ).fetchall():
            top = conn.execute(f"SELECT COALESCE(max({column}), 0) FROM {table}").fetchone()[0]
            conn.execute("SELECT setval(%s, %s, false)", [seq, top + 1])
        reader_role(conn, os.environ["GUIDANCE_READER_PASSWORD"])
    print("seed: done", flush=True)


if __name__ == "__main__":
    main()
