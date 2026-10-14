# Roadmap: from investigation agent to a hybrid AML case platform

Decided 2026-10-14 by the owner: build what works best for AML in a professional setting, not only an agent demo. The PRD remains background; this roadmap sets the order of work.

## Principle: each job goes to the tool that does it best

| Job | Done by |
|---|---|
| Raising and scoring alerts | Rules engine plus a graph-feature ML model |
| Identifying the pattern shape around an alert | Deterministic graph analytics |
| Preparing the case (network, history, evidence) | Code (case file) |
| Explaining, weighing context, recommending, writing the narrative | LLM |
| Deciding | Human investigator (with a second reviewer for escalations) |

Every step stays read-only, bounded, logged in the append-only audit trail, and measured. Results are on synthetic data and must be presented as a demonstration of design, not real-world performance.

## Phases

**A. Close the model question (now)**
- Validate the case-file design on the small model (6 dev alerts x 3).
- Price one `gemma4:cloud` case against the owner's quota, then compare models on the same alerts.

**B. Detection and alert scoring** (was PRD Sprint 5)
- Config-driven rules with reason codes: fan-in and fan-out bursts, rapid pass-through, round trips, structuring-like amounts, velocity, cross-border and currency mismatch.
- Graph-feature model (scikit-learn) scoring accounts; chronological split on the primary period; payment format excluded from headline numbers; rows after Sep 10 excluded.
- Alerts with a risk score and reason codes replace the label-built alerts as the case source; the label-built sets stay as a controlled benchmark.
- Metrics: PR-AUC against the base rate, precision at the top of the queue, alerts needed per true case, versus rules alone.

**C. Graph pattern identification**
- Deterministic motif detection around each alert (fan-in, fan-out, cycle, scatter-gather, gather-scatter, bipartite, stack, chain) with a confidence and the accounts involved.
- Compared against the LLM's pattern call on dev alerts; the better source feeds the case file.

**D. LLM analyst**
- Reads the case file and detection reasons; recommends escalate, close or more information, with reasons; drafts a suspicious-activity-style narrative.
- Measured on clearing false alarms safely (benign alerts closed without missing real ones), narrative quality, and cost.
- Ablations: no LLM, no case file.

**E. Guidance retrieval** (was PRD Sprint 3)
- Public AML typology guidance (FATF, FinCEN, FINTRAC), hybrid search, jurisdiction filter; narratives cite passages that are verified to exist.

**F. Case management UI (React)**
- React, TypeScript and Vite, served as a `ui` container behind the existing API.
- Enterprise look and feel modeled on common financial-crime case managers: dense data grids, a network view of the case, clear status and risk badges, keyboard-friendly review.
- Screens: alert queue (risk score, reason codes, status, age, assignee); case workspace (subject profile, interactive network graph of the case file with the pattern highlighted, transactions and evidence grid, AI narrative with verification and citation badges, decision panel with reason codes, second-reviewer approval for escalations); audit timeline; operations dashboard (alert volumes, false-alarm rate, model metrics); model governance page (model and prompt versions, evaluation results).
- Local login with roles (analyst, supervisor) for the four-eyes flow; no real authentication claims.

**G. Final evaluation and hardening**
- Freeze, then run the untouched evaluation set once on the chosen model; report with repeats and spreads.
- Prompt-injection tests on an added synthetic text field, least-privilege database role for the audit log, model cards, README with limitations.
