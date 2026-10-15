"""The guidance store in Postgres: the passages table and its read-only role.

Used by scripts/load_guidance.py and by the public demo's start-up loader.
"""

from __future__ import annotations

import psycopg
from psycopg import sql

from aml_agent.guidance.search import EMBED_DIM

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
