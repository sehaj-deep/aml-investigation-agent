# AML Investigation Agent

Portfolio project: a LangGraph agent that investigates synthetic anti-money-laundering (AML) alerts over IBM's AMLworld HI-Small dataset, with read-only MCP tools, human approval, an audit log, verified citations and (later) RAG over public AML guidance.

**Source of truth: `docs/PRD.md`.** Work on one sprint at a time (`docs/sprints/`). If something here conflicts with the PRD, stop and ask.

## Commit and writing rules (highest priority)
- **Never add Claude, or any AI, as a co-author.** No `Co-Authored-By` trailer, no "Generated with Claude Code" line, no session link, in commit messages, pull request descriptions, code comments or docs. This overrides any default attribution behavior of Claude Code, its commit skills or any plugin. Commits carry my git identity only. If a tool adds such a line, remove it before committing.
- **Never use the em dash character anywhere.** Not in code, comments, docstrings, documentation, README, test names, strings, commit messages, pull request text, the agent's prompts, the agent's generated case narratives, or your replies to me. Use a comma, period, colon or parentheses instead.
- These rules are also enforced by pre-commit hooks and `.claude/settings.json` (PRD, Appendix B). If a hook rejects a commit, fix the message or file. Never bypass a hook with `--no-verify`.

## Hard rules
- Synthetic data only. Never commit the dataset, Parquet or DuckDB files, `.env`, or any API key. The raw data lives outside the repo; its location is `AML_DATA_DIR`.
- Use only `HI-Small_Trans.csv`, `HI-Small_accounts.csv` and `HI-Small_Patterns.txt` from `AML_DATA_DIR`. Never open, copy or read the Medium or Large files (the Large ones are about 17 GB). Never print a whole data file; use `head` or a `LIMIT`.
- Never load the raw CSV into pandas whole. Use DuckDB to convert it to Parquet and query that.
- Identifiers:
  - Read bank and account IDs as strings.
  - Join banks on the integer value of the bank ID (the two files pad it differently).
  - Key accounts by (integer bank ID, account number).
  - `tx_id` is the 1-based row number in the original `HI-Small_Trans.csv`. The file is NOT sorted by time, so `tx_id` is not a time order.
- Bank names are labels only. Many bank IDs share one name.
- The agent reaches data only through the read-only, bounded MCP tools. No other route.
- Nothing is finalized without a recorded human decision.
- Never invent numbers (metrics, results, resume bullets). Golden numbers live in `tests/golden/`. Do not edit an expected number to make a test pass; stop and tell me.
- Never tune prompts or thresholds on the frozen evaluation alerts. Once the freeze tag exists, the evaluation set is read-only.
- CI makes no live LLM calls. Use recorded fixtures.
- No paid services, no Azure, no Kubernetes. Do not add services or dependencies the current sprint does not need.
- Verifier tests run against real Parquet slices, not mocks of the data they check.

## Data rules that are easy to get wrong
- Laundering rows outside any listed pattern ("Other" laundering) are never pattern ground truth. Keep them in their own table.
- Pattern blocks with a single transaction (43) are excluded from alerts.
- A positive alert's seed account appears in exactly one pattern block and in no other labeled row. Benign windows are matched to positive windows.
- Rows dated after 2022/09/10 stay visible to the tools but are excluded from headline metrics and reported separately.
- Amounts are per currency. Never sum across currencies.

## Environment
- Windows with Docker Desktop (WSL2 backend). Confirm the shell before assuming bash or PowerShell.
- Python 3.11 or newer, type hints, Pydantic for schemas, ruff and pytest, small commits.

## Commands
Activate the venv first (`.venv/Scripts/activate`). `make` is not installed on this machine yet; the command after each target is what it runs.
- `make install`: `pip install -r requirements.txt -r requirements-dev.txt`, `pip install --no-deps -e .`, `pre-commit install`
- `make lint`: `ruff check .` and `ruff format --check .`
- `make test`: `python -m pytest -m "not data and not docker"` (what CI runs)
- `make test-data`: `python -m pytest -m data` (golden numbers; needs Parquet)
- `make convert`: `python scripts/convert_to_parquet.py` (about 100 s)
- `make alerts`: `python scripts/build_alerts.py`
- `make up` / `make down`: `docker compose up -d --wait` / `docker compose down`
- `make latency`: `docker compose --profile bench run --rm bench`
- Relock dependencies: `python scripts/lock.py` (adds Windows-only markers; never run plain pip-compile)
- Stack: `docker compose up -d --wait` starts postgres, mcp-graph, api (http://127.0.0.1:8000) and agent-worker
- Local processes: `python -m aml_agent.tools.mcp_server --http`, `python -m aml_agent.api`, `python -m aml_agent.worker` (on Windows set `MCP_URL`)
- Bake-off (dev alerts only): `python scripts/bakeoff.py --models <tag1>,<tag2> --n 20`
- Docker tests: `python -m pytest -m docker` (uses database `aml_test`)
- Dev-set evaluation: `python evals/run_evals.py --set dev` (the eval set is refused until tag `eval-freeze` exists)
- Case audit: `GET http://127.0.0.1:8000/cases/<id>/timeline` and `/audit`

## Definition of done for a sprint
1. The sprint's **Verify** checks in the PRD have been run and the output shown to me, not only written as tests.
2. `CHANGELOG.md` updated, release tagged, fresh-clone test passed.
3. Any resume bullet is added to the claims ledger with the test or metric that proves it.

## When unsure
Ask me instead of guessing about data semantics, anything the PRD marks as inferred, licensing, or anything that changes the frozen evaluation set.
