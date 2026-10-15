# Changelog

## Unreleased: transaction monitoring
- Open-source XGBoost transaction monitoring model on IBM's 60/20/20 time split: test F1 71.2% with payment format, 64.1% without (paper: 28.7% to 63.2%); rules 10.9%. Figures without the rows after Sep 10 reported alongside.
- Alerts are accounts with suspicious transactions, each with its triggering transactions and top three SHAP factors; a seeded sample of 150 is the queue for the investigation evaluation.
- Tools show payment format and every date by default, as an analyst sees them.
- Alert policy: the threshold catches 84% of laundering accounts in validation at an industry-typical false-alarm rate; on test, 89.4% of laundering accounts are alerted (31,518 alerts, 93.8% false, in high, medium and low priority bands). Below-the-line testing: a random sample of 250 accounts just under the threshold is reviewed to measure misses.
- One alert queue (Postgres, paged): every alert shows its priority, reasons and flagged payments before it is opened; opening it starts the AI review, and the code-built evidence appears within seconds.
- Plain-language case screen and history; model and instruction versions only on the Governance page. Prompt p8 reads why the alert was raised.
- Decision records 0012 (first, account-level version), 0013 and 0014; scorecard part A updated.

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
