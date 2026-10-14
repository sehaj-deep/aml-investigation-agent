# Threat model (portfolio scope)

Synthetic data only; this is not a production system. Assets: integrity of case outputs, the audit trail, and the human-approval control.

| Threat | Control | Residual risk |
|---|---|---|
| Model writes or deletes data | Tools open a DuckDB file with `read_only=True`; no write tool exists; MCP refuses unknown tools | None found in tests |
| Model sees labels or ground truth | Tool DB holds no `is_laundering` column and no pattern or alert-truth tables; ground-truth files excluded from images | Payment format correlates with labels; hidden by default |
| Unbounded queries exhaust resources | Caps on hops, rows, windows and fan-out; Pydantic validation | Many small calls; limited by step and tool-call budgets |
| Model invents transactions or amounts | Model cites tx_ids only; code fetches evidence; verifier checks existence and every field against Parquet; grounding check | Narrative prose could still misstate numbers (not checked yet) |
| Case finalized without a human | Interrupt before finalize; finalize refuses without approve or reject; no finalize endpoint; decisions only on `pending_review` cases | Reviewer identity is self-declared (no auth in this phase) |
| Audit trail altered | Append-only triggers, revoked privileges, per-case hash chain | A superuser can drop triggers; edits are then detectable via the chain |
| Prompt injection via tool output | Data has no free text today; tools return structured JSON | Tested in Sprint 6 with an added synthetic text field |
| Secrets in repo or prompts | `.env` gitignored; no keys needed for the scripted provider; prompts carry only synthetic data | Free-tier providers may retain prompts (acceptable for synthetic data only) |
| Unauthenticated API | Bound to 127.0.0.1 in compose | No auth: local demo only |
