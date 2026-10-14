### Sprint 0: Foundation
**Build:** Repo, linting, pre-commit, CI skeleton, README stub. Convert `HI-Small_Trans.csv` to Parquet with DuckDB (explicit column names, string IDs, `tx_id` = row number). Load accounts, normalize bank IDs to integers for joins, and map each bank to a jurisdiction label (section 13). Parse patterns into tables, store the 1,968 labeled rows outside any pattern as `other_laundering`, and compute for each multi-row block the accounts that appear in no other block (seed-eligible). Seeded dev/eval alert generator. Docker Compose with Postgres. Investigate the 8 duplicate account numbers. Add `CLAUDE.md`, `docs/PRD.md` and `.env.example` (Appendix B).
**Done when:** `docker compose up` starts the stack and tests pass.
**Verify:**
- Golden-number tests assert the measured facts: 5,078,345 transactions, 5,177 labeled, 370 pattern blocks, 3,209 pattern rows, every pattern row matched to exactly one transaction, 43 single-row blocks, 1,968 labeled rows outside any pattern (all dated 09/01 to 09/10), 245 seed-eligible blocks, 30,470 bank IDs after integer normalization.
- Two conversion runs produce identical checksums.
- A fresh clone in a new folder starts the stack from scratch.
- A tool-query latency test reports p95 for neighbor lookups on the full table. Run it in the real Docker setup: if a bind mount from the Windows drive misses the 1 second target, move the Parquet files into a Docker named volume.
- The generated dev and eval sets share no pattern block.
- A test commit with a `Co-Authored-By` line is rejected, and a test commit containing an em dash is rejected (Appendix B).
- Every positive seed appears in exactly one pattern block and in no `other_laundering` row; every benign seed appears in no labeled row.
**Resume bullet:** none. This sprint does not merit one.
