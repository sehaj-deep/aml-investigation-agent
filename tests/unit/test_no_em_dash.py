"""Appendix B: no em dash in the agent's prompts or in recorded model outputs."""

from pathlib import Path

from aml_agent.agent import prompts

EM_DASH = chr(0x2014)
FIXTURES = Path(__file__).resolve().parents[2] / "evals" / "fixtures"


def test_prompts_have_no_em_dash():
    texts = [prompts.SYSTEM, prompts.HYPOTHESIZE, prompts.DRAFT]
    texts += [prompts.schema_retry("x"), prompts.budget_note("x"), prompts.reviewer_note("x")]
    texts.append(prompts.triage_message({"a": 1}, {"b": 2}))
    assert not any(EM_DASH in t for t in texts)


def test_recorded_fixtures_have_no_em_dash():
    for path in FIXTURES.rglob("*") if FIXTURES.exists() else []:
        if path.is_file():
            assert EM_DASH not in path.read_text(encoding="utf-8", errors="ignore"), path
