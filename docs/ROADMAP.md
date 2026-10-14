# Roadmap: from investigation agent to a hybrid AML case platform

Decided 2026-10-14 by the owner: build what works best for AML in a professional setting, not only an agent demo. The PRD remains background; this roadmap sets the order of work.

## Principle: each job goes to the tool that does it best

| Job | Done by |
|---|---|
| Raising and scoring alerts | Rules engine with an explainable risk score (an ML model is a later, optional extension) |
| Identifying the pattern shape around an alert | Deterministic graph analytics |
| Preparing the case (network, history, evidence) | Code (case file) |
| Explaining, weighing context, recommending, writing the narrative | LLM |
| Deciding | Human investigator (with a second reviewer for escalations) |

Every step stays read-only, bounded, logged in the append-only audit trail, and measured. Results are on synthetic data and must be presented as a demonstration of design, not real-world performance.

**Priority rule (owner, 2026-10-14):** no model fine-tuning and no complex ML for now. Important, visible product work comes first; trained detection models wait until the core is done.

**Order of work:** A (finish), C (done, measured), B, F with the copilot from D, E, G. Later and optional: H.

## Phases

**A. Close the model question (now)**
- Validate the case-file design on the small model (6 dev alerts x 3). Done.
- Measure pattern candidates plus the LLM on all 48 dev alerts. Running.
- Price one `gemma4:cloud` case against the owner's quota, then compare models on the same alerts.

**B. Rules-based detection and alert scoring** (was PRD Sprint 5, without the ML model)
- Config-driven rules with reason codes: fan-in and fan-out bursts on new (one-off) counterparties, rapid pass-through, round trips, structuring-like amounts, velocity, cross-border and currency mismatch.
- An explainable risk score: a weighted sum of rule hits, with each contribution shown to the investigator.
- Alerts with a risk score and reason codes become the case source; the label-built sets stay as a controlled benchmark.
- Payment format excluded from headline numbers; rows after Sep 10 excluded.
- Metrics: precision and recall of alerts against the labels, precision at the top of the queue, alerts per true case, and per-rule hit rates.

**C. Graph pattern identification**
- Deterministic motif detection around each alert (fan-in, fan-out, cycle, scatter-gather, gather-scatter, bipartite, stack, chain) with a confidence and the accounts involved.
- Compared against the LLM's pattern call on dev alerts; the better source feeds the case file.

**D. LLM analyst**
- Reads the case file and detection reasons; recommends escalate, close or more information, with reasons; drafts a suspicious-activity-style narrative.
- Measured on clearing false alarms safely (benign alerts closed without missing real ones), narrative quality, and cost.
- Ablations: no LLM, no case file.
- **Investigator copilot.** A chat agent attached to each case: the investigator asks questions ("who else did A4 pay?", "is this amount unusual for this account?", "show the money trail from A7") and the agent answers by calling the read-only MCP tools live, citing the transactions it used. Same controls as the case agent: bounded tools, step and token budgets, every call in the audit log, answers checked by the verifier, no write actions. Measured on a small set of scripted investigator questions with known answers (correct answer, tool calls, latency, cost).

**E. Guidance retrieval** (was PRD Sprint 3)
- Public AML typology guidance (FATF, FinCEN, FINTRAC), hybrid search, jurisdiction filter; narratives cite passages that are verified to exist.

**F. Case management UI (React)**
- React, TypeScript and Vite, served as a `ui` container behind the existing API.
- Enterprise look and feel modeled on common financial-crime case managers: dense data grids, a network view of the case, clear status and risk badges, keyboard-friendly review.
- Screens: alert queue (risk score, reason codes, status, age, assignee); case workspace (subject profile, interactive network graph of the case file with the pattern highlighted, transactions and evidence grid, AI narrative with verification and citation badges, decision panel with reason codes, second-reviewer approval for escalations); copilot chat panel beside the case (streaming answers, the tool calls it made, cited transactions highlighted in the network and grid); audit timeline; operations dashboard (alert volumes, false-alarm rate, model metrics); model governance page (model and prompt versions, evaluation results).
- Local login with roles (analyst, supervisor) for the four-eyes flow; no real authentication claims.

**H. Later, optional: ML detection**
- Done early, approved by the owner (2026-10-14): an open-source XGBoost model on account features, chronological split, compared against the rules (decision 0012, scorecard part A). It generates the alert queue for the investigation evaluation.

**G. Final evaluation and hardening**
- Freeze, then run the untouched evaluation set once on the chosen model; report with repeats and spreads.
- Prompt-injection tests on an added synthetic text field, least-privilege database role for the audit log, model cards, README with limitations.
