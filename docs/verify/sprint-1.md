# Sprint 1 Verify results

Run 2026-10-14. Model: **scripted provider only** (no live model is set up yet; see "Not done").

| Verify item | Result | Evidence |
|---|---|---|
| Writes through the tools fail; data connection read-only | Yes: DELETE, UPDATE, INSERT, DROP and CREATE all raise on the tool connection; no write tool exists; an unknown "delete" tool is refused by the MCP server | `tests/unit/test_graph_tools.py`, `tests/golden/test_tool_db.py` |
| Absurd hop or row requests capped; malformed arguments rejected | Yes: hops 1000 to 4, max_edges 10^6 to 300, limit 10^6 to 100, 499 tx_ids to 100, a year-long window clipped; string bank_id, negative hops, bad direction, SQL-like account, extra fields and reversed windows rejected | `tests/unit/test_graph_tools.py` |
| A deliberately looping alert stops at the step cap | Yes: stops at exactly 5 steps with `budget_exhausted = "step limit 5"`, then drafts and waits for review; tool-call and token caps also tested | `tests/unit/test_agent_graph.py` |
| Reaching finalize without a human decision is refused | Yes: `Command(goto="finalize")` on a paused case raises `FinalizeRefused`; malformed decisions fail validation; API has no finalize endpoint; decision on a non-pending case is 409 | `tests/unit/test_agent_graph.py`, `tests/docker/test_worker_api.py` |
| Kill the worker while a case is paused, restart, resume | Yes: hard kill of the worker process while `pending_review`, decision posted, new worker finalizes to `approved` with the identical draft | `tests/docker/test_worker_api.py` |
| Agent touches data only through MCP | Yes: tool DB has only `transactions` (no `is_laundering`) and `banks`; images exclude ground truth; tool results match independent Parquet queries on 6 dev alerts | `tests/golden/test_tool_db.py` |
| Run benign controls and count false escalations | **Not done**: needs a live model | |
| Bake-off table (tool-call validity, schema validity, steps, tokens, latency per model) | **Not done**: harness built and checked with the scripted provider (`scripts/bakeoff.py`); needs Ollama | |

Docker: `docker compose up -d --wait` starts postgres, mcp-graph, api and agent-worker, all healthy; a case created through the API ran to `pending_review` and was rejected through the API.

Test totals: 101 passed and 3 xfail (Sprint 0 definition questions) without Docker; 4 Docker tests passed.
