# 0007 Tool-query latency and Parquet mount

Status: measured (Sprint 0)

Benchmark: `scripts/bench_neighbors.py`, 1,000 seeded-random lookups of one account's non-self transactions (both directions) in a 2-day window over the full 5,078,345-row table. Target p95 under 1 second (PRD section 6).

Measured 2026-10-14 (16 GB Windows laptop, Docker Desktop WSL2, DuckDB 1.5.6):

| Where | Mode | p50 | p95 | p99 |
|---|---|---|---|---|
| Host | Parquet view (200 lookups) | 84 ms | 108 ms | 164 ms |
| Host | In-memory table | 25 ms | 30 ms | 34 ms |
| Docker, bind mount from D: | Parquet view | 181 ms | 222 ms | 241 ms |
| Docker, bind mount from D: | In-memory table | 13 ms | 19 ms | 24 ms |

Decision: the bind mount meets the target, so no named volume. Sprint 1 tools may load `transactions` into memory at startup for lower latency (about 10x faster); either way the connection the agent reaches stays read-only.
