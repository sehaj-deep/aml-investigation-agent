# 0009 Audit log, tracing and citation verification (Sprint 2)

Status: accepted (Sprint 2), pending owner review

**Audit log (`audit_log` table, `aml_agent/audit.py`).**
- One row per event: `case_created`, `decision_recorded` (API); `case_started`, `node_started`, `node_finished` (with the node's state delta), `node_interrupted`, `node_failed`, `model_call` (provider, model tag, prompt version, token counts, latency, the full reply), `tool_call` (name, arguments, result, timing, ok or error); `decision_applied`, `status` (worker).
- Each case's rows form a SHA-256 hash chain (`prev_hash`, `hash`, gapless `seq`), written under a per-case advisory lock.
- Triggers reject UPDATE, DELETE and TRUNCATE, and those privileges are revoked from PUBLIC. Limitation: a database superuser (the dev compose user) can drop triggers; the hash chain makes such edits detectable but not impossible. A production setup would use a separate least-privilege role.
- `reconstruct(events)` folds the node deltas back into the workflow state. Tests show the rebuilt state equals the live checkpoint exactly, in memory and in Postgres.
- If a worker dies mid-node, that node re-runs on restart and its events appear twice; the log stays truthful (both attempts happened) and the chain stays valid.

**Tracing (`aml_agent/tracing.py`).** OpenTelemetry SDK spans (`case.run`, `node.*`, `model.chat`, `tool.*`) exported straight into a Postgres `traces` table by a custom exporter. No otel-collector service: the collector has no Postgres exporter, and one fewer container suits 16 GB. Langfuse stays optional.

**Citation verification (`aml_agent/verify/citations.py`).** A `verify` node runs after `draft` and before review. It reads the Parquet source of truth through its own read-only path (not the agent's MCP tools). Checks: every tx_id the model cited exists (an invented ID fails even though it never becomes an evidence row); every evidence row matches on both parties, amount (exact decimal), currency and timestamp; no duplicate or uncited rows. A case is *faithful* if all pass. *Grounded* (every cited ID was returned by a tool during the case) is reported separately. Failures become `VERIFICATION_FAILED` warnings that the reviewer sees; approval is still possible, never silent.

**Evaluation harness (`evals/run_evals.py`).** Dev set only until the `eval-freeze` tag exists. Reports faithfulness, grounding, schema validity, pattern accuracy, evidence coverage, false escalations, latency and tokens, overall and split by alerts whose block runs past 2022/09/10.
