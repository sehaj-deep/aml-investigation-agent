# Changelog

## Unreleased: Sprint 0 (foundation), pending owner review before tag v0.1.0
- Scaffolding: packaging, pip-tools lockfiles with hashes, ruff, pytest, pre-commit hooks rejecting em dashes and AI co-author lines (both proven to reject), CI workflow with no data and no LLM calls.
- Data layer: DuckDB conversion of HI-Small to Parquet (`tx_id` = original row number, integer and raw bank IDs, DECIMAL amounts, `is_self_transfer`), deterministic byte-identical output with a checksum manifest.
- Tables: accounts, banks (jurisdiction rule from PRD section 13), pattern blocks and rows (each matched to exactly one transaction), other_laundering, pattern_accounts, seed_eligible (245 blocks).
- Golden-number tests for PRD Appendix A; three definition questions open.
- Seeded alert sets v1: dev 48 alerts, eval 80 alerts, half benign controls with matched activity and windows; labels in separate ground-truth files.
- Docker Compose: Postgres 17 with pgvector 0.8.0; latency benchmark p95 222 ms in Docker.
- Decision records 0001 to 0007.
