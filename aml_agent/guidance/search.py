"""Hybrid search over the guidance passages in Postgres (pgvector plus full-text search).

Two rankings are fused with reciprocal rank fusion (RRF):
- keyword: Postgres full-text search, any of the query's words (ts_rank_cd);
- meaning: cosine distance between embeddings (nomic-embed-text through Ollama, local).
If the embedding model is unreachable, the search falls back to keywords and says so.

The tool server connects with a read-only role (guidance_reader) that can only SELECT
from the guidance schema; see scripts/load_guidance.py.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import psycopg
from psycopg.rows import dict_row

from aml_agent import config  # noqa: F401  (loads .env)

EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
RRF_K = 60
CANDIDATES = 20
MAX_K = 8
MAX_TEXT = 1200


def ollama_url() -> str:
    """Ollama's address. host.docker.internal only resolves inside a container, so a
    process on the host itself (scripts, tests) uses 127.0.0.1 instead."""
    url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    if "host.docker.internal" in url and not os.path.exists("/.dockerenv"):
        url = url.replace("host.docker.internal", "127.0.0.1")
    return url


def embed(texts: list[str], kind: str, timeout: float = 30) -> list[list[float]]:
    """Embeddings for documents (kind="document") or a query (kind="query").

    nomic-embed-text expects a task prefix on each text. The connection timeout is short so
    that a search falls back to keywords quickly when the model is not reachable.
    """
    prefix = "search_document: " if kind == "document" else "search_query: "
    resp = httpx.post(
        f"{ollama_url()}/api/embed",
        json={"model": EMBED_MODEL, "input": [prefix + t for t in texts]},
        timeout=httpx.Timeout(timeout, connect=3),
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


def vector_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def reader_dsn() -> str:
    """Connection for searches: the read-only guidance role."""
    if dsn := os.environ.get("GUIDANCE_DSN"):
        return dsn
    user = os.environ.get("GUIDANCE_READER_USER", "guidance_reader")
    password = os.environ.get("GUIDANCE_READER_PASSWORD", "")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "aml")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


class GuidanceSearch:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or reader_dsn()

    def _rows(self, sql: str, params: list[Any]) -> list[dict]:
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5) as conn:
            return conn.execute(sql, params).fetchall()

    def keyword(self, query: str, n: int = CANDIDATES) -> list[str]:
        rows = self._rows(
            """
            WITH q AS (
                SELECT replace(plainto_tsquery('english', %s)::text, '&', '|')::tsquery AS q
            )
            SELECT id FROM guidance.passages, q
            WHERE q.q::text <> '' AND tsv @@ q.q
            ORDER BY ts_rank_cd(tsv, q.q) DESC, id
            LIMIT %s
            """,
            [query, n],
        )
        return [r["id"] for r in rows]

    def semantic(self, query: str, n: int = CANDIDATES) -> list[str]:
        vec = vector_literal(embed([query], "query")[0])
        rows = self._rows(
            "SELECT id FROM guidance.passages ORDER BY embedding <=> %s::vector, id LIMIT %s",
            [vec, n],
        )
        return [r["id"] for r in rows]

    def search(self, query: str, k: int = 5) -> dict:
        """The k best passages for the query, by fused keyword and meaning rankings."""
        k = max(1, min(k, MAX_K))
        rankings = {"keyword": self.keyword(query)}
        mode = "hybrid"
        if os.environ.get("GUIDANCE_SEARCH") == "keyword":
            mode = "keyword"  # no embedding model on this host
        else:
            try:
                rankings["meaning"] = self.semantic(query)
            except (httpx.HTTPError, KeyError, ValueError):
                mode = "keyword"  # embedding model unreachable: keywords only
        scores: dict[str, float] = {}
        for ranking in rankings.values():
            for rank, pid in enumerate(ranking, start=1):
                scores[pid] = scores.get(pid, 0.0) + 1.0 / (RRF_K + rank)
        top = sorted(scores, key=lambda pid: (-scores[pid], pid))[:k]
        if not top:
            return {"mode": mode, "passages": []}
        rows = {
            r["id"]: r
            for r in self._rows(
                "SELECT id, doc_id, title, publisher, url, page, section, jurisdiction, text "
                "FROM guidance.passages WHERE id = ANY(%s)",
                [top],
            )
        }
        passages = []
        for pid in top:
            r = rows[pid]
            passages.append(
                {
                    "passage_id": pid,
                    "source": r["title"],
                    "publisher": r["publisher"],
                    "jurisdiction": r["jurisdiction"],
                    "where": f"page {r['page']}" if r["page"] else r["section"],
                    "url": r["url"],
                    "text": r["text"][:MAX_TEXT],
                }
            )
        return {"mode": mode, "passages": passages}
