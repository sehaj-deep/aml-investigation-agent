"""Guidance lookup: quote checking, query building and passage splitting (no database)."""

from __future__ import annotations

from aml_agent.agent import prompts
from aml_agent.agent.graph import _check_guidance, _normalize
from aml_agent.guidance import search
from aml_agent.schemas.case import GuidanceQuote

PASSAGES = [
    {
        "passage_id": "fincen-fin-2014-a005-p1-2",
        "source": "FinCEN Advisory FIN-2014-A005",
        "jurisdiction": "US",
        "where": "page 1",
        "url": "https://www.fincen.gov/",
        "text": "This Advisory provides “red flags” that may assist financial "
        "institutions identify and report suspicious funnel account activity.",
    }
]


def test_exact_quotes_are_kept_and_others_reported():
    warnings: list[str] = []
    quotes = [
        # Straight quotes and different spacing still match the curly-quoted source.
        GuidanceQuote(passage_id="fincen-fin-2014-a005-p1-2", quote='provides "red  flags" that'),
        GuidanceQuote(passage_id="fincen-fin-2014-a005-p1-2", quote="funnel accounts are illegal"),
        GuidanceQuote(passage_id="made-up-1", quote="anything at all"),
    ]
    passages, citations = _check_guidance(PASSAGES, quotes, warnings)
    assert [c.quote_span for c in citations] == ['provides "red  flags" that']
    assert citations[0].source == "FinCEN Advisory FIN-2014-A005"
    assert passages[0]["quotes"] == ['provides "red  flags" that']
    assert any(w.startswith("GUIDANCE_QUOTE_NOT_FOUND") for w in warnings)
    assert any(w.startswith("GUIDANCE_NOT_FOUND: made-up-1") for w in warnings)


def test_normalize_ignores_typography():
    assert _normalize("Out‐of‑state  ‘deposits’") == "out-of-state 'deposits'"


def test_query_uses_guidance_language_and_red_flags():
    q = prompts.guidance_query("fan-in", ["Rapid onward transfers", "Flow-through activity"])
    assert q.startswith("funnel account")
    assert "Red flags: Rapid onward transfers; Flow-through activity" in q
    assert prompts.guidance_query(None, []) == prompts.TYPOLOGY_TERMS["none"]


def test_draft_prompt_lists_passages_by_id():
    block = prompts.guidance_block(PASSAGES)
    assert "passage_id=fincen-fin-2014-a005-p1-2 | FinCEN Advisory FIN-2014-A005 | page 1" in block
    assert "none were found" in prompts.guidance_block([])


def test_ollama_address_outside_docker(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/")
    assert search.ollama_url() == "http://127.0.0.1:11434"


def test_passages_hold_whole_sentences_within_the_size_limit():
    from scripts import build_guidance

    text = " ".join(f"Sentence number {i} is here." for i in range(100))
    chunks = build_guidance.windows(build_guidance.sentences(text), max_words=40)
    assert all(len(c.split()) <= 40 for c in chunks)
    assert all(c.endswith(".") for c in chunks)
    assert " ".join(chunks) == text
