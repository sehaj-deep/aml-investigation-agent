# AML Investigation Agent

A portfolio project: a LangGraph agent that investigates **synthetic** anti-money-laundering (AML) alerts over IBM's AMLworld HI-Small dataset, using read-only MCP tools, human approval, an audit log and verified citations.

**This is not a production AML system.** It runs only on synthetic data and free-tier tooling. Strong results here do not show it would work on real bank data.

Status: Sprint 0 (foundation). See `docs/PRD.md` and `docs/sprints/`.

## Data

The dataset is not in this repository. Download "IBM Transactions for Anti-Money Laundering (AML)" from Kaggle, keep only `HI-Small_Trans.csv`, `HI-Small_accounts.csv` and `HI-Small_Patterns.txt`, and set `AML_DATA_DIR` in `.env` (copy `.env.example`).

License: the dataset is published under the Community Data License Agreement, Sharing, Version 1.0 (CDLA-Sharing 1.0). This repository contains code, row-number identifiers and results only, never the data or bulk extracts.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/activate    # Windows; use .venv/bin/activate elsewhere
make install
make convert
make test-data
make up
```

## Citation

If you use this work, please cite the dataset authors:

- E. Altman, J. Blanusa, L. von Niederhausern, B. Egressy, A. Anghel, K. Atasu. "Realistic Synthetic Financial Transactions for Anti-Money Laundering Models." NeurIPS 2023, Datasets and Benchmarks Track. https://arxiv.org/abs/2306.16424
- B. Egressy, L. von Niederhausern, J. Blanusa, E. Altman, R. Wattenhofer, K. Atasu. "Provably Powerful Graph Neural Networks for Directed Multigraphs." AAAI 2024.
