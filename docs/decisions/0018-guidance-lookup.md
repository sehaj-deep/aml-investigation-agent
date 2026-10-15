# 0018 Guidance lookup (retrieval over public AML guidance)

Status: accepted (2026-10-14)

## Why

Investigators justify a typology and its red flags by pointing to regulatory guidance. The AI review, the copilot and the SAR draft should do the same, and every quote must be real.

## Sources (`guidance/SOURCES.md`)

Five US government publications, in the public domain:

- FFIEC BSA/AML Manual, Appendix F (red flags);
- FinCEN SAR narrative guidance (2003);
- FinCEN common SAR errors (2007);
- FinCEN Advisory FIN-2014-A005 (funnel accounts);
- FinCEN FIN-2006-G014 (shell companies).

FATF papers were left out: they are copyrighted, and reusing their text needs a licence check. `scripts/build_guidance.py` downloads the originals into `data/guidance/raw` (not committed; one PDF is over the repository's file-size limit) and writes 159 passages of about 125 words, with whole sentences, page numbers or section headings, to `guidance/passages.jsonl`. Tables of contents and page furniture are dropped.

## Search (`aml_agent/guidance/search.py`)

- **Store:** Postgres with pgvector. Passages carry a full-text index and 768-dimension embeddings from nomic-embed-text, which runs locally in Ollama with no quota (`scripts/load_guidance.py`).
- **Ranking:** hybrid. Keyword ranking (any of the query's words) and meaning ranking (cosine distance) are fused with reciprocal rank fusion. If the embedding model is unreachable, the search falls back to keywords and says so.
- **Access:** the MCP tool `search_guidance` (read-only, up to 8 passages, query of 3 to 300 characters) queries through the role `guidance_reader`, which can only read the guidance schema. A test shows it cannot read cases, insert or delete.

## Use

- **AI review (prompt p10):** after the pattern is named, code searches for the typology and the red flags that fired. The drafting step gets the top four passages and may cite one to three, each with a short exact quote. Code checks every quote word for word against its passage, ignoring case, spacing and quote styles. Quotes that are not there are dropped from the case and reported as warnings.
- **Copilot:** the copilot can call the tool for questions about typologies or reporting.
- **SAR draft (s3):** the checked quotes become facts; the narrative may name the source, and the downloaded report lists them.
- **Screen:** the AI assessment shows each cited quote with its source, page or section, and a link to the original.

## Measured (`evals/guidance_eval.py`, 18 investigator questions with known answer documents)

| Method | Right document first | In the top 3 | Mean reciprocal rank |
|---|---|---|---|
| Keyword | 77.8% | 88.9% | 0.856 |
| Meaning | 83.3% | 100% | 0.907 |
| Hybrid | 88.9% | 100% | 0.935 |

In a live review (gpt-oss:20b-cloud), the AI cited two quotes. One matched its FFIEC passage exactly and was kept; the other did not and was dropped with a warning.

## Limits

Five documents make document-level retrieval relatively easy; the score says little about a large corpus. The guidance is US-only, while the synthetic accounts span many jurisdictions.
