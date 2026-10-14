# 0008 Investigation agent design (Sprint 1)

Status: accepted (Sprint 1), pending owner review

- **Only route to data.** The agent calls tools only through the MCP client (`aml_agent/tools/client.py`) to the `mcp-graph` server. The server opens `tools.duckdb` with `read_only=True`. That file holds `transactions` without `is_laundering` and `banks`; no pattern, label or alert tables. Ground-truth files are excluded from the Docker image.
- **Bounds.** Hops capped at 4, counterparties at 100, trace edges at 300 (20 per account per hop), tx_ids per lookup at 100, windows clipped to the data and to 31 days. Caps are reported in `capped`; malformed arguments are rejected by Pydantic (`extra="forbid"`, account pattern, ranges).
- **The model names tx_ids; code writes the evidence.** The draft reply lists `evidence_tx_ids`; the evidence rows (parties, amount, currency, time) are fetched with `get_transactions`. FR-3: the LLM does no lookups code can do. Cited tx_ids that no tool returned during the case, or that do not exist, are flagged as warnings. Evidence amounts are exact decimal strings (FR-4 shows a float; changed for exact verification).
- **Payment format is hidden from the tools by default** (`TOOLS_SHOW_PAYMENT_FORMAT=false`), because nearly all labeled rows are ACH and the agent could learn the generator's habit. Superseded by 0013: shown by default.
- **Budgets.** Per review round: 12 model steps, 20 tool calls; per case: 120,000 tokens; at most 2 "request more" rounds. On exhaustion the agent is told and must hypothesize.
- **Structured replies.** JSON validated with Pydantic, one retry with the error. Two failures give a visible `MODEL_OUTPUT_INVALID` warning and a `needs_more_info` draft, never a silent default.
- **Em dash guard.** Prompts forbid it; code also removes it from narrative fields and records a warning.
- **Human approval.** LangGraph `interrupt` before `finalize`; the resume value must validate as a `Decision`; `finalize` raises `FinalizeRefused` without an approve or reject. The API has no finalize endpoint.
- **Persistence.** LangGraph `AsyncPostgresSaver` (thread_id = case_id) plus a `cases`/`decisions` work queue claimed with `FOR UPDATE SKIP LOCKED` and a lease.
- **Provider interface.** `ChatProvider` with `ollama` (LangChain ChatOllama, retry with backoff) and `scripted` (deterministic policies for tests and CI; its numbers are harness checks, not model results).
- **Windows note.** psycopg async needs the selector event loop, which cannot spawn subprocesses, so on Windows the worker reaches MCP over HTTP (`MCP_URL`), as it does in Docker.

## Update 2026-10-14: giveaways hidden (owner decision)

Two signals reveal the label without investigation: payment format (nearly all laundering is ACH) and dates after Sep 10 (only laundering, per the dataset author). Both are hidden from the tools by default (`TOOLS_SHOW_PAYMENT_FORMAT=false`, `TOOLS_SHOW_LATE_ROWS=false`): windows are clipped to 2022-09-10 23:59 and `get_transactions` treats later rows as not found. This is also realistic, since an investigator on Sep 10 cannot see the future. Both stay switchable so one comparison run can show how much each giveaway would inflate results. Superseded by 0013: both are shown by default, as an analyst would see them. The verifier still checks citations against the full Parquet data.

## Update 2026-10-14: hub hints and a group-transfers tool

Live runs on dev alerts showed the small model missing hub accounts and citing the seed's ordinary activity. Two plain-code tool additions help any model:
- `get_neighbors` reports, for each counterparty, `their_senders` and `their_receivers` (distinct accounts it is paid by and pays in the window), so a hub stands out without one lookup per account.
- `get_transfers_among(accounts, window)` returns only transfers whose sender and receiver are both in a chosen group (2 to 30 accounts, at most 300 transfers), plus group accounts with no link to the rest. The agent uses it to collect a pattern's own transfers as evidence.
Both are read-only, bounded and validated like the other tools.

## Update 2026-10-14: code-built case file and code-collected evidence (prompt p4)

Measured on the 24 dev positives before building (no model involved): 84% of each pattern's transactions are connected to the seed at all (bipartite and stack blocks are often disjoint pieces); the seed's two-step neighborhood holds 75%; a perfect choice of pattern accounts followed by `get_transfers_among` gives 100% coverage at 92% precision.

So exploration and evidence collection moved into code, leaving the model the judgment:
- **Case file (triage).** Code builds it through the same MCP tools and audit trail: seed summary, step-1 counterparties, step-2 counterparties of every step-1 account with at most 40 counterparties (up to 25 expansions), and loops through the seed found by 8-step forward and backward traces (an account the seed's money reaches that earlier sent money reaching the seed). Accounts get labels A0 (seed), A1, ... Median size about 600 tokens, at most about 2,900 on dev alerts; it holds 77% of each dev pattern on average.
- **Hypothesis.** The model returns the pattern and `pattern_accounts` (labels, "bank/account" or objects). Accounts no tool ever returned are dropped with a warning.
- **collect_evidence (new code node).** Evidence is the transfers among the named accounts plus the seed in the alert window (at most 60 rows), shown to the model before it drafts.
- **Draft.** Narrative, action, confidence and limitations only.
- Trace hop cap raised from 4 to 8 (chain patterns reach 8 steps on dev alerts).
