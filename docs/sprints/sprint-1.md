### Sprint 1: Investigation agent
**Build:** Read-only MCP graph server over DuckDB. LangGraph workflow (triage, investigate, hypothesize, draft, human-approval interrupt, finalize). FastAPI endpoints. Seed-based alerts including benign controls. Step and token budgets. Dev-tier model. A small bake-off (about 20 dev alerts) across candidate models.
**Done when:** An alert goes in and a drafted case waits for approval. Resuming with a decision finalizes it. The agent touches data only through the MCP tools.
**Verify:**
- Writes through the tools fail (and the data connection is read-only).
- Absurd hop or row requests are capped; malformed arguments are rejected.
- A deliberately looping alert stops at the step cap.
- Reaching `finalize` without a human decision is refused.
- Kill the worker while a case is paused, restart, and resume to completion.
- Run benign controls and count false escalations.
- The bake-off table reports tool-call validity, schema validity, steps, tokens and latency per model.
**Resume bullet template:**
> Built a LangGraph agent with a read-only MCP tool layer that investigates synthetic AML alerts from a single seed account and drafts structured case summaries, with checkpointed human approval before any case is finalized. Compared [N] open models on tool-call validity ([X]%) and citation faithfulness.
