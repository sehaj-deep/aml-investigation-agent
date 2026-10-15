"""Guidance search on the real Postgres store (needs docker compose up and
scripts/load_guidance.py), and the reader role's least privilege."""

from __future__ import annotations

import psycopg
import pytest

from aml_agent.guidance.search import GuidanceSearch, reader_dsn

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def guidance():
    g = GuidanceSearch()
    try:
        if not g.keyword("funnel account"):
            pytest.skip("guidance not loaded; run scripts/load_guidance.py")
    except psycopg.Error as exc:
        pytest.skip(f"guidance store not reachable: {exc}")
    return g


@pytest.mark.parametrize(
    ("query", "doc_id"),
    [
        ("funnel account cash deposits withdrawn in another location", "fincen-fin-2014-a005"),
        ("shell company with no physical presence moving funds", "fincen-fin-2006-g014"),
        ("five essential elements of a SAR narrative who what when", "fincen-sar"),
    ],
)
def test_search_finds_the_right_document(guidance, query, doc_id):
    out = guidance.search(query, 3)
    assert out["passages"], out
    assert any(p["passage_id"].startswith(doc_id) for p in out["passages"])
    assert all(p["url"].startswith("https://") and p["text"] for p in out["passages"])


def test_reader_role_can_only_read_guidance(guidance):
    with psycopg.connect(reader_dsn(), autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM guidance.passages").fetchone()[0] > 100
        for sql in (
            "SELECT count(*) FROM public.cases",
            "DELETE FROM guidance.passages",
            "INSERT INTO guidance.passages (id) VALUES ('x')",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(sql)
