# Changelog

## Unreleased: Sprint 2 (audit and faithfulness), pending owner review and a live model
- Append-only, hash-chained audit log of every model call, tool call, state change and decision; UPDATE, DELETE and TRUNCATE blocked; a case rebuilt from the log alone matches the live run exactly.
- OpenTelemetry traces exported to a Postgres `traces` table.
- Citation verifier on the Parquet source of truth, run before review; failures are visible warnings. Corruption test: 288 of 288 corruptions flagged, no false alarms on 24 clean cases.
- API: `GET /cases/{id}/audit` and `/timeline`. Evaluation harness `evals/run_evals.py` (dev set only until the freeze tag).
- Threat model.

## Unreleased: Sprint 1 (investigation agent), pending owner review and a live model
- Read-only tool database (no labels) and four bounded graph tools served over MCP: get_account_summary, get_neighbors, trace_funds, get_transactions.
- LangGraph workflow: triage, tool loop with step, tool-call and token budgets, hypothesize, draft, human-approval interrupt, finalize (refused without a decision). Postgres checkpoints; evidence rows filled by code from tx_ids.
- Provider interface with Ollama and a deterministic scripted provider; bake-off harness on dev alerts.
- FastAPI cases and review API (no finalize endpoint), Postgres work queue, agent worker; Docker services mcp-graph, api, agent-worker.
- Kill-and-resume verified; bake-off and false-escalation count wait for a live model.

## Unreleased: Sprint 0 (foundation), pending owner review before tag v0.1.0
- Scaffolding: packaging, pip-tools lockfiles with hashes, ruff, pytest, pre-commit hooks rejecting em dashes and AI co-author lines (both proven to reject), CI workflow with no data and no LLM calls.
- Data layer: DuckDB conversion of HI-Small to Parquet (`tx_id` = original row number, integer and raw bank IDs, DECIMAL amounts, `is_self_transfer`), deterministic byte-identical output with a checksum manifest.
- Tables: accounts, banks (jurisdiction rule from PRD section 13), pattern blocks and rows (each matched to exactly one transaction), other_laundering, pattern_accounts, seed_eligible (245 blocks).
- Golden-number tests for PRD Appendix A; three definition questions open.
- Seeded alert sets v1: dev 48 alerts, eval 80 alerts, half benign controls with matched activity and windows; labels in separate ground-truth files.
- Docker Compose: Postgres 17 with pgvector 0.8.0; latency benchmark p95 222 ms in Docker.
- Decision records 0001 to 0007.
