# AML Investigation Agent

A portfolio project: a LangGraph agent that investigates **synthetic** anti-money-laundering (AML) alerts over IBM's AMLworld HI-Small dataset, using read-only MCP tools, human approval, an audit log and verified citations.

**This is not a production AML system.** It runs only on synthetic data and free-tier tooling. Strong results here do not show it would work on real bank data.

Status: investigation agent, controls, code-built case file, typology indicators, rules-based risk indicators and the case-management UI are built. Measured results, with their caveats, are in [`docs/SCORECARD.md`](docs/SCORECARD.md); the plan is in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## What it does

An alert (one seed account and a time window) goes in. A LangGraph agent investigates the transaction graph only through read-only, bounded MCP tools, proposes a pattern, and drafts a case whose evidence rows are fetched by code. A verifier checks every cited transaction against the data, the case pauses for a human decision, and every step is written to an append-only, hash-chained audit log, with traces in Postgres.

Services (`docker compose up -d --wait`): `postgres` (with pgvector), `mcp-graph` (tools), `api` (http://127.0.0.1:8000), `agent-worker`.

| Endpoint | Purpose |
|---|---|
| `POST /cases` with `{"alert_id": "dev-0001"}` | Queue a case |
| `GET /cases?status=pending_review` | Cases waiting for review |
| `GET /cases/{id}` | Draft, evidence, verification, warnings, metrics |
| `POST /cases/{id}/decision` | `approve`, `reject` or `request_more`, with a reason and reviewer |
| `GET /cases/{id}/timeline` | What the agent did, read from the audit log |

There is no endpoint that finalizes a case.

## Limitations

Synthetic data only; results would not transfer to real bank data. Alerts are built from the dataset's labels (no monitoring system yet). The tools see every bank's transactions, which no real institution can. The US jurisdiction label is inferred from bank names and currencies. No authentication: local demo only. See `docs/threat_model.md`.

## Data

The dataset is not in this repository. Download "IBM Transactions for Anti-Money Laundering (AML)" from Kaggle, keep only `HI-Small_Trans.csv`, `HI-Small_accounts.csv` and `HI-Small_Patterns.txt`, and set `AML_DATA_DIR` in `.env` (copy `.env.example`).

License: the dataset is published under the Community Data License Agreement, Sharing, Version 1.0 (CDLA-Sharing 1.0). This repository contains code, row-number identifiers and results only, never the data or bulk extracts.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/activate    # Windows; use .venv/bin/activate elsewhere
make install
make convert       # about 2 minutes; Parquet tables and the read-only tool DB
make test-data
make up            # postgres, mcp-graph, api, agent-worker
```

Without a model, the stack runs with `LLM_PROVIDER=scripted` (deterministic, for tests). For real runs, install Ollama, sign in, and set `LLM_PROVIDER=ollama` and `LLM_MODEL` in `.env`.

## Citation

If you use this work, please cite the dataset authors:

- E. Altman, J. Blanusa, L. von Niederhausern, B. Egressy, A. Anghel, K. Atasu. "Realistic Synthetic Financial Transactions for Anti-Money Laundering Models." NeurIPS 2023, Datasets and Benchmarks Track. https://arxiv.org/abs/2306.16424
- B. Egressy, L. von Niederhausern, J. Blanusa, E. Altman, R. Wattenhofer, K. Atasu. "Provably Powerful Graph Neural Networks for Directed Multigraphs." AAAI 2024.
