"""Load the guidance passages into Postgres with embeddings, and set up the reader role.

    python scripts/load_guidance.py

Needs the Postgres container and Ollama with nomic-embed-text (ollama pull
nomic-embed-text; it runs locally, no quota). Creates the schema `guidance` with full-text
and vector (pgvector, HNSW) indexes, replaces its passages, and creates the role
`guidance_reader` (password GUIDANCE_READER_PASSWORD) that can only read that schema: the
tool server searches through it.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import psycopg
from psycopg import sql

from aml_agent import store
from aml_agent.guidance.search import EMBED_DIM, embed, vector_literal

ROOT = Path(__file__).resolve().parents[1]
PASSAGES = ROOT / "guidance" / "passages.jsonl"
BATCH = 32

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS guidance;
CREATE TABLE IF NOT EXISTS guidance.passages (
    id           TEXT PRIMARY KEY,
    doc_id       TEXT NOT NULL,
    title        TEXT NOT NULL,
    publisher    TEXT NOT NULL,
    url          TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    page         INTEGER,
    section      TEXT,
    text         TEXT NOT NULL,
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    embedding    vector({EMBED_DIM}) NOT NULL
);
CREATE INDEX IF NOT EXISTS passages_tsv_idx ON guidance.passages USING gin (tsv);
CREATE INDEX IF NOT EXISTS passages_vec_idx ON guidance.passages
    USING hnsw (embedding vector_cosine_ops);
"""


def reader_role(conn: psycopg.Connection, password: str) -> None:
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'guidance_reader'").fetchone()
    verb = "ALTER" if exists else "CREATE"
    conn.execute(
        sql.SQL("{} ROLE guidance_reader LOGIN PASSWORD {}").format(
            sql.SQL(verb), sql.Literal(password)
        )
    )
    db = conn.execute("SELECT current_database()").fetchone()[0]
    conn.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO guidance_reader").format(sql.Identifier(db))
    )
    conn.execute("REVOKE ALL ON SCHEMA public FROM guidance_reader")
    conn.execute("GRANT USAGE ON SCHEMA guidance TO guidance_reader")
    conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA guidance TO guidance_reader")


def main() -> None:
    password = os.environ.get("GUIDANCE_READER_PASSWORD")
    if not password:
        raise SystemExit("set GUIDANCE_READER_PASSWORD in .env")
    rows = [json.loads(line) for line in PASSAGES.read_text(encoding="utf-8").splitlines()]
    started = time.perf_counter()
    vectors: list[list[float]] = []
    for i in range(0, len(rows), BATCH):
        vectors += embed([r["text"] for r in rows[i : i + BATCH]], "document", timeout=300)
    print(f"embedded {len(rows)} passages in {time.perf_counter() - started:.0f} s")
    with psycopg.connect(store.database_url(), autocommit=True) as conn:
        conn.execute(SCHEMA)
        with conn.transaction():
            conn.execute("TRUNCATE guidance.passages")
            with conn.cursor().copy(
                "COPY guidance.passages (id, doc_id, title, publisher, url, jurisdiction, page, "
                "section, text, embedding) FROM STDIN"
            ) as copy:
                for r, v in zip(rows, vectors, strict=True):
                    copy.write_row(
                        [
                            r["id"],
                            r["doc_id"],
                            r["title"],
                            r["publisher"],
                            r["url"],
                            r["jurisdiction"],
                            r["page"],
                            r["section"],
                            r["text"],
                            vector_literal(v),
                        ]
                    )
        reader_role(conn, password)
    print(f"loaded {len(rows)} passages into guidance.passages; role guidance_reader is set up")


if __name__ == "__main__":
    import psycopg.sql  # noqa: F401  (used through psycopg.sql above)

    main()
