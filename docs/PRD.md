# AML Investigation Agent

**Product requirements document (PRD) and project plan**
Version 0.7 · October 2026 · Status: planning complete enough to start Sprint 0

> **Name.** The project is called what it does: an agent that investigates anti-money-laundering (AML) alerts. Repository: `aml-investigation-agent`. Python package: `aml_agent`. Earlier drafts used invented working names (Ledgerlens, Casethread); both were dropped because a reader could not tell from them what the project is.
> This is a personal portfolio project built on **synthetic data only** and **free-tier tooling**. It is not a production AML system and must never be described as one.

## What changed in v0.7

- **Appendix B now lists everything needed before the first Claude Code session**: installed tools, git identity, the Docker memory cap, how to give Claude Code access to the dataset folder, and the three files to place in the repo. Earlier versions left these out.
- A ready-made `settings.json` (attribution off) is provided as its own file.
- The commit-message hook now also rejects the "Claude-Session" trailer and claude.ai session links.

## What changed in v0.6

- **Two repo-wide rules added** (Appendix B and `CLAUDE.md`): Claude is never listed as a co-author or generator in commits or pull requests, and the em dash character is never used anywhere. Both are enforced by git hooks and a project setting, not only by instructions, because instructions alone can be overridden by tool defaults.

## What changed in v0.5

- **Location decided.** The project lives in `D:\Coding\AI_Agents\aml-investigation-agent`, next to the `archive` dataset folder (I confirmed the folder exists). Implementation is done with Claude Code; Appendix B gives the setup, a working loop, and a ready Sprint 0 prompt, and a `CLAUDE.md` file is provided separately.
- **Rows dated after 09/10: decided without waiting for the authors' reply** (section 10). They stay visible to the agent's tools but are excluded from every headline metric and reported separately. This choice can only make results more conservative, so a later reading of the authors' reply cannot invalidate it.
- **New leak closed.** If benign alerts never had windows reaching past 09/10 but positives did, the alert window alone would reveal the label. Benign windows are now matched to positive windows (section 10).
- **Resume milestone stated (section 4).** Minimum to list: Sprints 0 to 3. Recommended finish line: Sprints 0 to 4.

## What changed in v0.4

You pasted the Kaggle dataset page, so the facts below are now **documented** rather than inferred.
- **Confirmed by the Kaggle page:** laundering that follows none of the 8 listed patterns exists ("not all laundering in the data follows one of these 8 patterns"); the HI-Small row of the dataset table lists 5.1K laundering transactions at 1 per 981 (the "3.6K" I quoted from a paper summary was wrong); the Small datasets cover Sep 1 to 10; the license is **CDLA-Sharing 1.0**; the authors recommend a **chronological 60/20/20** split; the authors cite the whole-ecosystem view as a feature (a real bank sees only its own slice).
- **One correction.** The page says transactions after the primary date range are "all laundering". In your HI-Small file that is not exactly true: 1,108 rows fall after 09/10, 655 (59%) are labeled laundering and 453 are unlabeled ACH rows. The authors' longer reply on that point is linked from the page but was not in the paste.
- **New measured facts:** the transactions file is not sorted by timestamp, so sort before any chronological split. The 60% and 80% timestamp cutoffs are 2022/09/06 13:36 and 2022/09/08 16:12.
- **Design changes:** Sprint 5 uses the authors' 60/20/20 chronological split, handles the post-09/10 rows separately, and no longer demands that train and test accounts be disjoint (that is not how this benchmark is meant to be used). Added a license note, a citation duty, and an optional "single-institution view" experiment.

## What changed in v0.3

- **The LLM's role is stated plainly (section 12 rewritten).** The LLM is the core of the product: it is the investigator. Rules appear in exactly two places: (a) a rules engine that *creates alerts* (Sprint 5), and (b) a plain-code investigator used as a *control group* in one experiment (the "no-LLM ablation", Sprint 4), so the project can show with numbers what the LLM adds.
- **Open data questions resolved (section 10, new subsection "Resolved data questions").** The 1,968 labeled rows outside any pattern are the generator's "Other" laundering; the 43 single-row blocks are degree-1 patterns by design; the ~39% of accounts with non-"Country Bank" names are a pool of US-style bank names (supported by currency evidence).
- **New data findings that change the design.** Background activity covers only 2022/09/01 to 09/10 (the 8 days after it, 09/11 to 09/18, hold only a thin tail of mostly-laundering transactions); pattern accounts are reused across blocks, so alert seeds must come from accounts unique to one block; payment format leaks the label; bank IDs are spelled with different zero-padding in the two files.
- **Alert construction updated** (seed selection rule, per-type counts recomputed), **Sprint 0 checks and Sprint 5 time split updated**, and **Appendix A expanded**.
- Provenance is now explicit: each data fact is marked as *documented* (paper), *measured* (my analysis of your files) or *inferred*.

Earlier (v0.2): dataset inspected; hardware and compute decided (cloud model, CPU embeddings, Kaggle only for download); dev-tier/report-tier model strategy; jurisdiction-aware retrieval; verification checks in every sprint; cost wording corrected (free of charge, but needs free accounts and stays within free-tier quotas).

---

## 1. Summary

The AML Investigation Agent is an agentic investigation assistant for anti-money-laundering (AML) analysts. Given an alert, a LangGraph agent investigates the transaction graph through a read-only tool layer (MCP), grounds its reasoning in public AML guidance (RAG), drafts a cited case summary, and **pauses for a human investigator's approval** before anything is finalized. Every tool call and decision is logged, and every claim in a drafted narrative is verified programmatically against the underlying data.

The project is built in **sprints**. Each sprint ends with a tagged release, a working demo, and a measured result that can go on a resume.

### Why this project

It matches what financial institutions and consultancies are hiring AI developers to build. Research on current postings and company announcements (October 2026) showed these recurring themes:

| Theme | Evidence |
|---|---|
| Agent orchestration with LangGraph | Deloitte, Citi, Manulife and bank postings name LangGraph |
| MCP tool servers | A bank agentic-AI posting asks for building MCP servers and making agent behavior auditable; a traded-risk posting wants MCP integrations to internal risk systems |
| Human approval checkpoints | The traded-risk posting wants approval checkpoints for any agent action with financial or regulatory consequence; Bank of America wants human-in-the-loop review and auditable logs |
| RAG with evaluation | Deloitte postings ask for Ragas or DeepEval; the traded-risk posting wants RAG over policy and regulatory documents to ground outputs |
| Guardrails, observability, audit evidence | Bank of America postings ask for LLM-as-a-judge evaluation, guardrails, and audit-friendly traceability |
| Production-grade, not proof of concept | A Deloitte senior consultant posting asks for production-grade agentic experience, not just POCs |
| Model risk governance | OSFI Guideline E-23 takes effect May 1, 2027; a traded-risk posting mentions SR 11-7-style validation |
| Hybrid classical ML plus agents | A Deloitte AI/ML posting asks for prototyping classical models for hybrid AI systems |

Goldman Sachs publicly described building agents with Anthropic for trade accounting and client onboarding, and Citi (Arc) and Manulife (an enterprise agent platform with Agent 365 governance) are building governed agent platforms. This project is a small-scale demonstration of the same pattern: **agents plus the controls regulated firms require.**

---

## 2. Goals and non-goals

### Goals
1. Demonstrate an agent that does real investigative work (multi-step tool use over a graph), not just summarization.
2. Demonstrate the controls banks require: scoped tool access, human approval, audit trail, tracing, and verified citations.
3. Produce **measured** results: faithfulness, retrieval quality, latency, cost, and (Sprint 5) detection quality.
4. Show what the LLM adds over a deterministic pipeline (the ablation in section 12).
5. Be reproducible by a stranger with `docker compose up` plus two free accounts.
6. Be explainable in an interview in under five minutes, with honest limitations.

### Non-goals
- Not a real-time transaction-monitoring system.
- Does not file suspicious activity reports (SARs). It drafts a case summary for a human investigator.
- No real customer data, ever.
- No paid cloud, and no deployed hosting (most free tiers require a card).
- No Kubernetes in this phase. Services stay stateless and configured through environment variables, so a later move is a packaging change.
- No fine-tuning of language models.
- No claim that it works for all institutions (see section 13).

---

## 3. Users and use cases

**Primary persona: AML investigator (simulated).** Receives alerts, needs a fast, evidence-backed first draft of a case, and keeps final authority.

| Use case | Description |
|---|---|
| Investigate an alert | Agent starts from a seed account and time window, follows counterparties, and tests pattern hypotheses |
| Draft a case summary | Structured narrative with transaction evidence and guidance citations |
| Approve, reject or request more | Human reviews the draft; the agent resumes from a checkpoint with the decision |
| Audit a past case | Reconstruct exactly what the agent did and saw |
| Evaluate a change | Run the eval harness to see whether a prompt, model or retrieval change helped or hurt |

---

## 4. Scope by sprint

Alerts in Sprints 1 to 4 are constructed from the dataset's **ground-truth pattern files** (standing in for an upstream monitoring system). Sprint 5 adds a rules engine and a detection model that generate alerts instead. The README says this openly. Real banks also separate monitoring from investigation.

| Sprint | Theme | Core deliverable |
|---|---|---|
| 0 | Foundation | DuckDB/Parquet data layer, golden-number tests, alert-set generator, Compose + CI skeleton |
| 1 | Investigation agent | LangGraph + read-only MCP graph tools + human approval + small model bake-off |
| 2 | Audit and faithfulness | Audit log, tracing, programmatic citation verification |
| 3 | RAG over AML guidance | Hybrid retrieval, jurisdiction tags, `retrieve_guidance` tool, retrieval metrics |
| 4 | Evaluation, ablation and final run | Regression gates, no-LLM ablation, final reported run on the stronger model |
| 5 | Rules-based alerting and detection model | Rules alerting, graph features, ML model, end-to-end on generated alerts |
| 6 | Hardening | Prompt-injection tests, optional sandboxed code step, model card |

### When is it resume-ready?

Counting Sprint 0 (the foundation, which earns no bullet), the project becomes resume-worthy in stages:

| Stop after | What you can honestly claim | Verdict |
|---|---|---|
| Sprint 1 | A LangGraph agent with a read-only MCP tool layer and checkpointed human approval, plus a model bake-off | Not yet. No measured accuracy and no grounding. List it only as "in progress" |
| Sprint 2 | Adds an audit log, tracing and verified citations with a measured faithfulness rate | Decent, but missing RAG, which these roles ask for |
| Sprint 3 | Adds hybrid-search RAG over AML guidance with jurisdiction filtering and measured retrieval quality | **Minimum to put on a resume.** It covers the full stack: agent, MCP tools, human approval, audit, RAG |
| Sprint 4 | Adds CI evaluation gates, the no-LLM comparison, and a frozen final run on a stronger model | **Recommended finish line.** It has measured results and answers "why an LLM?" with data |
| Sprint 5 | Adds a rules-based alerting layer and a detection model | Extension. Makes the pipeline end to end |
| Sprint 6 | Adds prompt-injection red-teaming and model cards | Extension. Adds a security story |

**Plan to complete Sprints 0 to 4: five sprints.** At the rough pace of 1 to 2 weeks per part-time sprint, that is about 5 to 10 weeks; treat this as a guess, since model quotas and debugging can stretch it. If time runs short, stop after Sprint 3 and describe Sprint 4 as next steps. Sprints 5 and 6 are optional.

---

## 5. Functional requirements

### FR-1 Alert intake
- An alert contains an ID, a **seed account** (and optionally a trigger transaction) and a time window. It does **not** contain the other accounts or the pattern type.
- Design reason: if the alert lists every account in the pattern, the agent has little to discover and "evidence coverage" becomes trivial. The agent must find the rest through the tools.
- **Seed rule:** the seed must be an account that appears in exactly one listed pattern block and in no other labeled row (section 10). Pattern accounts are reused across blocks, so any other seed would make the "true pattern" ambiguous.
- Alerts include **benign controls** so the agent can legitimately conclude "no suspicious pattern." An agent tested only on positives proves little.
- Accounts are identified by (bank ID as an integer, account number). Bank names are display labels only, because many banks share one name (section 10).

### FR-2 Graph investigation tools (MCP server, read-only)
- `get_account_summary(account_id)`: transaction counts and totals **per currency**, counterparties, time span
- `get_neighbors(account_id, direction, window)`: counterparties and their transactions
- `trace_funds(account_id, hops, window)`: bounded multi-hop path tracing
- `get_transactions(ids)`: raw transaction records
- All tools are read-only, bounded (hop, row and time limits), and validated with Pydantic schemas.
- Amounts are reported per currency. The file has separate received and paid currency columns, so tools never sum across currencies without an explicit conversion rule. Check how many rows have different received and paid currencies in Sprint 0.
- The agent has **no other route** to the data.

### FR-3 Investigation workflow (LangGraph)
- Nodes: triage → investigate (tool loop with step budget) → hypothesize pattern → retrieve guidance (Sprint 3) → draft case → **human approval interrupt** → finalize.
- Checkpointed state, so a paused case survives a restart and resumes with the human decision.
- Hard limits on steps, tool calls and tokens per case.
- Deterministic logic stays deterministic. The LLM is not asked to do arithmetic or ID lookups that code can do.

### FR-4 Case output (structured)
```json
{
  "case_id": "...",
  "pattern_hypothesis": "fan-out | fan-in | cycle | gather-scatter | scatter-gather | bipartite | stack | random | none",
  "summary": "...",
  "evidence": [{"tx_id": 0, "from_bank": "...", "from_account": "...", "to_bank": "...", "to_account": "...", "amount_paid": 0.0, "currency_paid": "...", "timestamp": "..."}],
  "guidance_citations": [{"chunk_id": "...", "source": "...", "jurisdiction": "...", "quote_span": "..."}],
  "recommended_action": "escalate | close | needs_more_info",
  "confidence": "low | medium | high",
  "limitations": "..."
}
```
The dataset has no transaction ID, so `tx_id` is the 1-based row number in `HI-Small_Trans.csv` (header excluded). It is assigned once in Sprint 0 and never changes.

### FR-5 Human review
- A simple API endpoint (and optionally a minimal UI) to list pending cases, view the draft with its evidence and warnings, and submit approve, reject or request-more with a reason.
- Nothing is marked final without a recorded human decision.

### FR-6 Audit and traceability (Sprint 2)
- Append-only audit log in Postgres: every tool call (inputs, outputs, timing), model call metadata (provider, model tag, prompt version, token counts), state transition, and human decision.
- Any case can be reconstructed from the log.
- OpenTelemetry traces are stored first in Postgres. Self-hosted Langfuse is added only if memory allows (see section 6).

### FR-7 Faithfulness verification (Sprint 2)
- Programmatically verify that every cited transaction exists and that its parties, amounts, currencies and timestamp match the data.
- Cases that fail verification are flagged and cannot proceed to approval without a visible warning.

### FR-8 Retrieval over AML guidance (Sprint 3)
- Corpus: public AML guidance on typologies and red flags. **Check each source's terms; link to originals rather than redistributing.**
- Chunking, local embeddings, hybrid search (vector + Postgres full-text), jurisdiction filter, optional reranking.
- `retrieve_guidance(pattern, query, jurisdiction)` is exposed as an MCP tool, so retrieval has the same permissions and audit trail as everything else.
- Citation verification: each cited chunk must exist in the index, and the quoted span must actually appear in it.

### FR-9 Evaluation harness (Sprint 4)
- Runs the frozen evaluation alert set end to end and reports the metrics in section 11.
- CI runs only deterministic checks and recorded fixtures, never live model calls.

### FR-10 Rules-based alerting and detection model (Sprint 5)
- A rules engine (amount thresholds, structuring, velocity, cycles) and a graph-feature classifier produce alerts that feed the agent. This mirrors a real bank, where plain rules and ML decide *whether an alert fires* and the investigation happens *afterwards*.
- The rules engine is also the benchmark the ML model must beat.
- The LLM never decides whether an alert fires.

### FR-11 Hardening (Sprint 6)
- Prompt-injection test suite against tool outputs.
- Optional sandboxed code-execution step.
- Generated model card per agent.

### FR-12 Deterministic comparison pipeline (Sprint 4)
- A second, plain-code investigator (fixed graph queries, rule-based pattern classification, templated narrative, no LLM) that takes the same alerts and returns the same case schema. It exists only to be compared with the agent (section 12). It is not a product feature.

---

## 6. Non-functional requirements

| Area | Requirement |
|---|---|
| Cost | No money spent. Needs two free accounts (Kaggle for the dataset download, Ollama for the cloud model) and stays inside free-tier usage limits |
| Hardware | Built for 16 GB RAM and an integrated GPU. Docker Desktop memory capped at about 6-8 GB so Windows keeps headroom |
| Reproducibility | One command to start; pinned dependencies; seeded alert generation; documented data download; model tag and prompt version recorded in every run |
| Safety | Read-only tools; no network egress from any code-executing component; synthetic data only |
| Data privacy | Prompts leave the machine (cloud model). Only synthetic data and public guidance may ever be sent |
| Observability | Every case fully traceable |
| Performance | Report latency, tokens and tool-query latency per case. Tool queries should be fast enough to be invisible next to model latency (target p95 under 1 second, to be measured in Sprint 0) |
| Portability | Stateless services, environment-based config, model provider behind one interface |
| Documentation | README with architecture diagram, results, limitations, and a threat model |

---

## 7. Architecture

```
                       ┌────────────────────────────┐
  Alert source ───────►│  FastAPI                   │◄──── Human investigator
  (pattern files,      │  (cases, review, health)   │      (approve / reject / more)
   later rules + ML)   └─────────────┬──────────────┘
                                     │
                       ┌─────────────▼──────────────┐
                       │  LangGraph workflow        │
                       │  triage → investigate →    │
                       │  hypothesize → retrieve →  │
                       │  draft → [HUMAN APPROVAL]  │
                       │  → finalize                │
                       │  (checkpointed state)      │
                       └───┬─────────────────┬──────┘
                 MCP calls │                 │ model calls
            ┌──────────────▼───┐   ┌─────────▼──────────────┐
            │ MCP: graph tools │   │ LLM provider (config): │
            │ (read-only)      │   │  Ollama cloud, or      │
            ├──────────────────┤   │  optional Gemini key   │
            │ MCP: guidance    │   │ Embeddings: local, CPU │
            │ retrieval        │   └────────────────────────┘
            └───────┬──────────┘
                    │
   ┌────────────────▼───────┐   ┌───────────────────────┐   ┌─────────────────────────┐
   │ DuckDB + Parquet       │   │ Postgres              │   │ OpenTelemetry           │
   │ transactions (read-only│   │ • case store          │   │  → Postgres trace table │
   │ to tools)              │   │ • audit log (append)  │   │  → Langfuse (optional)  │
   └────────────────────────┘   │ • pgvector + FTS      │   │  → Grafana (optional)   │
                                │ • LangGraph checkpoints│   └─────────────────────────┘
                                └───────────────────────┘
```

### Case lifecycle

1. An alert (seed account + time window) is created from the dataset's pattern files.
2. A case is stored and the workflow starts.
3. The agent triages, then investigates only through the read-only MCP tools, within a step budget.
4. It forms a pattern hypothesis, or concludes there is none.
5. From Sprint 3, it retrieves guidance for that pattern and the case's jurisdiction.
6. It drafts the structured case output.
7. Ordinary code verifies every cited transaction and guidance quote. Failures are flagged.
8. The workflow pauses at the human approval interrupt. State is checkpointed.
9. The investigator approves, rejects or asks for more. A recorded decision is required to finalize.
10. Every step is written to the audit log and traces.

### Docker Compose services (target)

| Service | Purpose | Sprint |
|---|---|---|
| `postgres` (with pgvector) | Cases, audit log, checkpoints, vectors, traces | 0 |
| `mcp-graph` | Read-only transaction-graph tools over DuckDB/Parquet | 1 |
| `api` | FastAPI: cases and review | 1 |
| `agent-worker` | LangGraph workflow runner | 1 |
| `otel-collector` | Trace pipeline | 2 |
| `mcp-guidance` | Retrieval tool server | 3 |
| `langfuse` (and its dependencies) | LLM trace UI. Heavy for 16 GB, so add last and check its current self-hosting requirements | 2+, optional |
| `grafana` | Dashboards | optional |

The Ollama app runs on the Windows host (it provides both the cloud-model endpoint and local embeddings), and containers reach it through the Docker host gateway. Verify this setup in Sprint 1. Design rules: stateless services, config through environment variables, no secrets in the repo.

---

## 8. Tools and technologies

**Core** = needed for the project to make sense. **Optional** = add if time allows.

### Language and libraries
| Tech | Role | Tier |
|---|---|---|
| Python | Everything | Core |
| DuckDB + Parquet | Query the full dataset without loading it into RAM | Core |
| pandas, NumPy | Small result sets and analysis | Core |
| networkx | Graph construction and traversal on extracted neighborhoods | Core |
| Pydantic | Schemas, validation of tool I/O and case output | Core |

### Agent layer
| Tech | Role | Tier |
|---|---|---|
| LangGraph | Workflow, state, checkpointing, human-approval interrupts | Core |
| LangChain | Model wrappers, structured output, tool bindings, retrievers | Core |
| MCP (Model Context Protocol) | Tool servers for graph access and guidance retrieval | Core |
| FastAPI | API for cases and review | Core |
| Ollama | Cloud model access (free tier) and local CPU embeddings | Core |
| Gemini API (AI Studio key) | Optional backup LLM provider | Optional |
| smolagents | Sandboxed code-writing analysis step | Optional (Sprint 6) |

### Retrieval
| Tech | Role | Tier |
|---|---|---|
| pgvector | Vector store inside Postgres | Core (Sprint 3) |
| Postgres full-text search | Keyword half of hybrid search | Core (Sprint 3) |
| Local embedding model | Via Ollama or sentence-transformers, on CPU | Core (Sprint 3) |
| Document parsing (Docling or similar) | Turning guidance PDFs into chunks | Core (Sprint 3) |
| Reranker | Retrieval quality | Optional |

### Detection and baselines (Sprint 5)
| Tech | Role | Tier |
|---|---|---|
| Plain Python, config-driven thresholds | Rules-based alert generation (Sprint 5) and the no-LLM comparison pipeline (Sprint 4) | Core (Sprint 4-5) |
| scikit-learn | Baseline model and metrics | Core (Sprint 5) |
| XGBoost or LightGBM | Stronger baseline | Optional |
| PyTorch Geometric | Graph neural network, would need a GPU | Dropped unless you have one |

### Safety and controls
| Tech | Role | Tier |
|---|---|---|
| Least-privilege MCP tools | Agent reaches data only through read-only, bounded tools | Core |
| Human-in-the-loop interrupt | No finalization without a human decision | Core |
| Docker sandbox (no network, read-only data) | Required if a code-executing agent is used | Core if used |
| Presidio | PII detection, to show the pattern even on synthetic data | Optional |
| Guardrails AI or similar | Output validation | Optional |

### Observability and evaluation
| Tech | Role | Tier |
|---|---|---|
| OpenTelemetry | Tracing | Core |
| Postgres trace store | Default trace destination | Core |
| Langfuse (self-hosted) | Trace UI for LLM calls | Optional (memory permitting) |
| Grafana | Dashboards | Optional |
| pytest + GitHub Actions | Eval harness and CI gates | Core |
| Ragas or DeepEval | RAG metrics, LLM-as-judge | Core (Sprints 3-4) |
| MLflow | Experiment tracking | Optional |

### Infrastructure
| Tech | Role | Tier |
|---|---|---|
| Docker Desktop + Compose (WSL2) | Local runtime | Core |
| Postgres | Case store, audit log, vectors, checkpoints | Core |

**Deliberately not used:** Azure or any paid cloud, Kubernetes (for now), Kaggle notebooks (the project is a multi-service system, and no step needs a GPU), LangSmith paid tiers, fine-tuning.

### Azure AI Foundry mapping (for README and interviews)
Foundry appears often in Manulife and Deloitte postings. This project does not use it, but you can show you understand the mapping:

| This project | Foundry equivalent |
|---|---|
| pgvector + FTS | Azure AI Search |
| Presidio / Guardrails AI | Azure AI Content Safety (Prompt Shields, etc.) |
| OpenTelemetry + trace store | Application Insights tracing via Azure Monitor |
| Human approval interrupt | Approval gates in agent workflows |
| Ragas / DeepEval | Foundry built-in evaluators (groundedness, task adherence, tool accuracy) |
| Environment-variable credentials | Entra ID / managed identity, keyless auth |

Be honest in interviews: you built on open tooling and studied how it maps to Foundry. Microsoft maintains a `langchain-azure-ai` integration, so porting a LangGraph app is a realistic later step.

---

## 9. Model strategy

The agent uses a cloud-hosted model through the Ollama free tier. Two things drive the plan: free-tier usage limits are the real constraint (not your hardware), and results must be comparable and honest.

### Free-tier facts (verify in your own account before relying on them)
- Ollama's free plan has light cloud usage, session limits that reset every 5 hours, weekly limits that reset every 7 days, and one concurrent cloud model (Ollama's cloud page).
- A community guide classifies cloud models by usage level: `gpt-oss:20b-cloud` as low; `gemma4:cloud`, `gemma4:31b-cloud`, `gpt-oss:120b-cloud`, `qwen3.5:cloud` and `nemotron-3-super:cloud` as medium; `deepseek-v4-pro:cloud` as extra high. This is a secondary source. Confirm what your account can actually run.
- Ollama occasionally retires cloud models. Keep the model tag in config.
- Cloud usage is measured mainly by GPU time, so token counts alone won't predict quota use.

### Two tiers

| Tier | Purpose | Model (starting candidates) | Alert set used |
|---|---|---|---|
| **Dev tier** | Building, debugging, prompt iteration, CI fixtures | A low-usage model, for example `gpt-oss:20b-cloud` | Dev alerts only |
| **Report tier** | The numbers you publish | The best performer from the bake-off, among candidates such as `gemma4:31b-cloud`, `gpt-oss:120b-cloud`, `qwen3.5:cloud` | Frozen evaluation alerts |

Public benchmarks do not clearly separate these models for agent work (vendor-reported tool-use scores for Gemma 4 31B and Qwen models are close, and aggregator comparisons of Gemma 4 31B and gpt-oss-120b on agentic tasks are within noise and flagged as low confidence). They also measure different tasks from yours. Decide with a bake-off on your own task.

### Rules for switching models without cheating
1. **Freeze before the final run.** Prompts, schemas, tool definitions, step budgets and thresholds are frozen and tagged before the report-tier run. Never tune on the evaluation alerts.
2. **Keep alert sets separate.** Dev alerts and evaluation alerts never overlap (section 10).
3. **Run the bake-off in Sprint 1** on about 20 dev alerts across the candidates, scoring valid tool-call rate, schema-valid output rate, steps per case, citation faithfulness, tokens and latency. Use only dev alerts, so the evaluation set stays untouched.
4. **Report both tiers side by side** in the final results. Showing that the pipeline works on a cheap model and improves on a stronger one demonstrates a model-agnostic design.
5. **One model per published table.** Never mix models inside one reported evaluation. Record provider, exact tag, prompt version, date and seed in every eval report.
6. **Use a different model as judge when you can.** A model grading its own output is biased. State which models generated and judged.
7. **Replays test the harness, not the model.** Cached responses make development free, but numbers from a cached replay are not model results. The final report-tier run is uncached.

### Quota plan
- Measure tokens and wall-clock time per case during Sprint 1-2 on the dev tier, then estimate the cost of one full evaluation run against your weekly limit.
- Cache dev-tier responses by hash of (model, prompt, tool results).
- Keep a run manifest, so a final run that hits a limit can resume across days without redoing finished cases.
- If a final run cannot complete on one provider's free tier, a free Gemini key is a switchable fallback, but it counts as a different model and must be reported as such.
- Add retry with backoff for rate-limit errors.

### Data handling
- Free tiers send prompts off your machine. Gemini's unpaid terms state that Google may use submitted content to improve its products and that human reviewers may read it. That is acceptable only because every input here is synthetic or public.
- Never put credentials, personal data or private documents into prompts.

---

## 10. Data

### Primary dataset: IBM AMLworld, HI-Small
- Synthetic transactions from IBM Research and ETH Zurich, generated by an agent-based simulator, with transaction-level laundering labels and listed laundering patterns. Published on Kaggle as "IBM Transactions for Anti-Money Laundering (AML)". Kaggle lists the license as **CDLA-Sharing 1.0**. As I understand that license (it is not legal advice; read the full text at the Community Data License Agreement site before publishing): using the data and publishing your own analysis, code and results is fine, but if you *share the data itself or modified copies of it*, you must do so under the same license with its notices. So: do not commit the CSV, the Parquet files or bulk transaction extracts to a public repo; commit scripts, row-number alert IDs and results instead. CI fixtures hold small excerpts of transactions (recorded tool outputs); either keep them small and add the license notice, or generate them from clearly synthetic rows. Cite the authors' papers in the README.
- Your folder contains all six sizes (HI/LI × Small/Medium/Large). **Use HI-Small only.** The Large transaction files are about 17 GB each and do not belong on a 16 GB machine. Do not copy the other files into the project repo.

### Facts about HI-Small, with provenance

Each fact is marked **[documented]** (stated in the AMLworld paper or its NeurIPS supplement), **[measured]** (my analysis of your files, October 2026; details in Appendix A) or **[inferred]**.

- **Size and labels [documented + measured].** 5,078,345 transactions; 518,573 unique account numbers in the accounts file; 5,177 transactions labeled laundering (about 1 per 981). The Kaggle page's dataset table lists 515K accounts, 5M transactions, 5.1K laundering transactions and 1 per 981 for HI-Small, which matches the file. (An earlier summary of the paper's Table 4 showed "3.6K"; that was a misreading and is superseded.)
- **Time [documented + measured].** The Kaggle page and paper say the Small datasets span Sep 1 to 10 (10 days) and call this the "primary" period of activity. In your file, background transactions cover **2022/09/01 to 09/10** (207K to 1.1M rows per day). The dates 09/11 to 09/18 hold 1,108 rows (396 on 09/11 falling to 11 on 09/18): 655 (59%) are labeled laundering and 453 are unlabeled ACH rows. The page acknowledges transactions after the primary period and says a user observed they are "all laundering"; that does not hold exactly in this file, and the authors' fuller reply (linked from the page) was not in the paste. Either way, a row dated after 09/10 is a strong time leak: 59% laundering versus 0.1% overall.
- **Patterns [measured].** 370 listed laundering patterns across 8 types, covering 3,209 transactions. Every pattern row matched exactly one labeled row in the main file.
- **No transaction ID column [measured].** The project assigns `tx_id` = row number (FR-4).
- **No free-text field [measured].** The prompt-injection tests in Sprint 6 need an added, disclosed synthetic text field.
- **License and citation [documented].** Kaggle lists the license as **Community Data License Agreement, Sharing, Version 1.0**. The page asks users who publish work built on the data or code to cite the authors' papers: the AMLworld paper (NeurIPS 2023), and the paper "Provably Powerful Graph Neural Networks for Directed Multigraphs". See the license note below.
- **Recommended split [documented].** Each dataset "can be subset chronologically for train, validate, and test"; the authors found a **60% / 20% / 20%** division effective. Sprint 5 follows it.
- **Whole-ecosystem view [documented].** The page stresses that a real institution sees only the transactions that touch it, while this dataset contains the whole financial ecosystem. This agent's tools also see every bank's transactions, which a single real institution could not. State that in the README (section 13 adds an optional experiment).
- **Payment format leaks the label [measured].** Pattern rows are 3,208 ACH plus 1 Bitcoin, although ACH is only 11.8% of all rows (600,797). At least 4,395 of the 5,177 labeled rows (85%) are ACH (3,208 pattern rows plus 1,187 isolated "Other" rows). A detector that sees payment format can learn the generator's habit instead of laundering behavior.

### Resolved data questions

| Question | Answer | Evidence | Confidence |
|---|---|---|---|
| What are the 1,968 labeled rows that are in no listed pattern? | They are the dataset's **"Other" laundering**: laundering that the generator makes happen outside the eight named patterns. They are real labels, not errors, and not part of any pattern block. | **Documented:** the Kaggle page says "not all laundering in the data follows one of these 8 patterns" and that the generator tracks illicit funds "through arbitrarily many transactions", so laundering many steps from its source is labeled too; the paper says laundering "is not limited to specific patterns", and its Table 8 (for LI-Large) splits laundering transactions into pattern and "Other": 81,143 "Other" and 19,461 in patterns. The supplement describes the non-pattern group as "the integration transactions disguised as other activities (e.g. employee payroll or company supplies)". **Measured (HI-Small):** all 1,968 fall between 09/01 and 09/10. Only 25 have a sender that earlier received a labeled row (versus 1,395 of 3,209 pattern rows), so they are not mostly chain continuations. Rows that share accounts form 1,297 groups: 1,238 are isolated single transfers (1,187 ACH, 31 Bitcoin, 20 Cheque) and 59 are larger groups, including cash, cheque and credit-card fan-out-like structures (largest: 247 rows, 5 senders to 238 receivers; next: 159 rows, 2 senders to 156 receivers; several of 21 to 29 rows from one sender). | High that laundering outside the 8 patterns exists (documented on the Kaggle page and in the paper). That these exact 1,968 rows are the paper's "Other" category is an inference: the paper's table is for LI-Large and I found no HI-Small breakdown. |
| Why do 43 pattern blocks contain a single transaction? | They are patterns the generator produced with **degree 1**. Not truncation, not a file error. | **Measured:** the Patterns file header of each block carries the generator parameter, for example "Max 16-degree Fan-Out" or "Max N hops" (RANDOM). Single-row FAN-OUT, FAN-IN and RANDOM blocks have degree or hops equal to 1. The 18 single-row BIPARTITE blocks have no parameter and are one 1-to-1 transfer. 42 of the 43 involve accounts that appear in other labeled pattern blocks; none touch an "Other" row. Only 1 falls on 09/01 and none on the last two days of the file, so the file edges do not explain them. **Documented:** the Kaggle page says the Patterns files list transactions following the 8 patterns of Suzumura and Kanezashi's AMLSim simulator; neither it, the paper nor the supplement discusses single-transfer patterns. | High for the mechanism (it is in the headers). Not confirmed by the authors. |
| Why do about 39% of accounts have bank names that are not "<Country> Bank #N"? | A separate pool of **US-style bank names** (468 distinct names, such as "First Bank of Tampa", "Savings Bank of Omaha", "National Bank of Laramie"), shared by many bank IDs. | **Measured:** 201,078 accounts (about 39%) use these names. The pool is Bank of / First Bank of / Savings Bank of / National Bank of followed by 54 US place names, plus Thrift, Bancorp, Credit Union and invented brand names. About 23 bank IDs share each name on average (10,885 bank IDs, 468 names). Each bank ID has exactly one name. The 33 other labels (UK, Canada, Germany, ... and "Crytpo", sic) use "<Label> Bank #N". **Currency check:** payments sent from US-style-named banks are 81% US dollars; each country label matches its national currency (Canada 91% Canadian dollar, UK 88% UK pound, Germany 98% euro, Switzerland 96% Swiss franc, Japan 85% yen); the "Crytpo" banks are 100% Bitcoin. **Documented:** the paper, supplement and Kaggle page do not describe bank naming or say these are US banks. | High that they are US-style banks (currency evidence), but "US" is inferred, not documented. |
| Why does the background data stop at 09/10? | The Small dataset simulates 10 days. Pattern transactions that begin late carry on after the background ends. | **Documented:** 10 days (Kaggle table and paper Table 4); the page calls it the "primary" period and notes later transactions. **Measured:** see "Time" above. | High |
| Are pattern accounts unique to one pattern? | No. 100 of 3,170 pattern accounts appear in more than one block; 138 of the 327 multi-row blocks share an account with another block; 245 of the 327 have at least one account that appears in no other block. | **Measured** | High |

**What the Kaggle page does and does not cover.** I now have its text (pasted by you). It documents the dataset table, the license, the 60/20/20 split advice, the existence of laundering outside the 8 patterns, and the origin of the 8 patterns (AMLSim). It does **not** document the column definitions, the bank naming scheme, single-transaction patterns, or the structure of the non-pattern laundering. It also refers to a reply to a user (Marco Pianta) about transactions after the primary date range; that reply is linked but was not in the paste. If you paste it, I will fold it into the Sprint 5 split rule.

### Loading gotchas
- The transactions header has two columns both named `Account`. Rename them explicitly to `from_account` and `to_account`. A default pandas read renames them silently.
- Read bank and account IDs as **strings**, never numbers. The transactions file zero-pads bank IDs with inconsistent widths (for example bank 10 appears as `010` and `0010`; 58 of 30,470 banks appear under two spellings). The accounts file stores bank IDs **without** padding (`210`, `331579`). Join on the **integer value** of the bank ID. I checked that no account is split by this: each (bank, account) pair appears under exactly one spelling.
- Bank names are not unique (about 23 bank IDs share each US-style name). Identify a bank by its ID, never by its name.
- The transactions file is **not sorted by timestamp** (checked). Sort before any chronological split or time-windowed scan. `tx_id` stays the original file row number, so it is an identifier, not a time order.
- Account numbers are not strictly unique in the accounts file (8 duplicates found). Key accounts by (integer bank ID, account), and investigate those 8 in Sprint 0.
- Do not read the CSV into pandas whole. Convert it once to Parquet with DuckDB, then query it from DuckDB.
- About 11.6% of rows (591,212) are transfers from an account to itself. Decide in Sprint 0 whether tools hide them, label them, or include them, and document the choice.

### Decision: rows dated after 09/10

I am not waiting for the authors' reply on this, because the following rule is safe under any answer.
1. **Keep the rows in the data** (DuckDB and Parquet) and visible to the agent's tools. About one fifth of pattern rows (the 655 labeled rows after 09/10 are all pattern rows, since "Other" laundering stops on 09/10) belong to blocks that begin earlier, and hiding them would give the agent incomplete patterns.
2. **Exclude them from every headline metric.** For the detection model (Sprint 5) they are not in train, validation or test. For the agent evaluation, windows and ground truth are unchanged, but results are also reported with and without alerts whose blocks run past 09/10, to show the effect.
3. **Report them separately** as a "late rows" side table with the warning that the timestamp alone predicts the label (59% laundering versus 0.1% overall).
4. **Revisit only if the authors' reply says something that conflicts.** The choice can only make headline numbers more conservative, so it cannot overstate results.

### Why not random subsampling
Random row sampling breaks the graph (neighbors disappear). Instead, keep the full HI-Small in DuckDB/Parquet and subsample the **alert set**, not the data. I have not benchmarked query speed on your machine, so Sprint 0 includes a latency test with a target of p95 under 1 second per tool call.

### Alert set construction
- **Positives:** a pattern block from `HI-Small_Patterns.txt` with at least two transactions (327 of 370 blocks; the 43 single-row blocks are excluded). The alert carries one seed account and a time window around the block, not the full account list (FR-1). The window runs from shortly before the block's first transaction to shortly after its last, so some windows extend past 09/10.
- **Seed rule:** the seed is an account that appears in exactly one pattern block and in no `other_laundering` row, chosen by a seeded random draw from the block's eligible accounts. 245 of the 327 blocks have at least one such account. Eligible blocks per type: BIPARTITE 28, CYCLE 40, FAN-IN 29, FAN-OUT 32, GATHER-SCATTER 33, RANDOM 24, SCATTER-GATHER 30, STACK 29. Every type has well over the 8 needed (3 dev plus 5 evaluation). Sprint 0 re-counts after also checking the "no other labeled row" condition.
- **Negatives (benign controls):** seed accounts that appear in no labeled row at all, matched on activity (transaction count and degree). **Window matching:** each benign alert takes its window start and length from the empirical distribution of the positive alerts' windows, including windows that run past 09/10, so the window dates alone cannot reveal the label. Where a benign window runs past 09/10 it simply contains whatever rows exist.
- **Dev/eval split (starting proposal, adjust after measuring tokens per case):**
  - Dev set: 3 positives per type (24) plus 24 benign controls.
  - Frozen evaluation set: 5 positives per type (40) plus 40 benign controls.
  - Seeded generation; blocks never appear in both sets; the evaluation set is versioned and never used for tuning.
- **"Other" laundering rows:** stored in their own table. Never used as pattern ground truth, and "evidence coverage" counts only transactions in the pattern block. They are not agent alerts in this plan (most are isolated single transfers with no structure to investigate). In Sprint 5 they count as labeled positives for the detection model, and detection results are reported both on all labeled rows and on pattern rows only.

### Guidance corpus (Sprint 3)
See section 13.

### Data caveats to state in the README
- Synthetic data. Strong results do **not** show the system would work on real bank data.
- Severe class imbalance (about 0.1% laundering).
- Alert seeds and windows are constructed from labels, not produced by a monitoring system, until Sprint 5.
- Pattern names in the dataset do not map one-to-one to real-world typology language.
- Background activity covers 10 days, and some laundering labels belong to an "Other" category outside the listed patterns.
- Nearly all labeled laundering is ACH, so detection results must be shown with and without payment format.
- Bank locations are inferred from bank names and currencies; the dataset does not document them.
- The dataset authors themselves caution that performance "might not translate one-to-one to real data".

---

## 11. Evaluation plan and metrics

| Metric | Definition | Sprint |
|---|---|---|
| Tool-call validity | % of model tool calls that are well-formed and accepted | 1 |
| Schema validity | % of case outputs that parse against the case schema | 1 |
| Citation faithfulness | % of cases where every cited transaction exists and matches (ID, parties, amounts, currencies, timestamp) | 2 |
| Evidence coverage | Share of the true pattern block's transactions that the case evidence includes | 2-4 |
| Pattern accuracy | Agent's hypothesis vs the pattern type of the source block (including "none" for benign controls) | 2-4 |
| False escalation rate | Benign controls the agent recommends escalating | 2-4 |
| Retrieval recall@k | Does the correct guidance passage appear in the top k | 3 |
| Citation validity | % of guidance citations whose quoted span exists in the cited chunk | 3 |
| Jurisdiction leakage | % of cases citing guidance from the wrong jurisdiction | 3 |
| Context precision / recall | Ragas metrics over the retrieval set | 3-4 |
| Narrative quality | LLM judge, **validated against a small human-labeled set**, agreement reported | 4 |
| Ablation deltas | LLM agent vs the no-LLM comparison pipeline (section 12) on pattern accuracy, coverage, false escalations, cost | 4 |
| Latency, tokens, tool-query time per case | Median and p95 | 1-4 |
| Detection quality | Precision, recall, PR-AUC, F1 with the authors' chronological **60/20/20** split of the 09/01 to 09/10 primary period (section 10) | 5 |
| Injection resilience | Utility under attack vs without, before and after defenses | 6 |

### Principles
- Prefer **programmatic** checks over LLM judges wherever possible. They are free, deterministic and harder to argue with.
- A judge is only as good as its agreement with human labels. Report the agreement and the limitation.
- Report failures. A candid failure analysis is more credible than a perfect score.
- Never invent numbers. Resume bullets get filled in only after measurement.

---

## 12. The role of the LLM, and the no-LLM comparison

### 12.1 The short version

**The LLM is the core of this project. It is the investigator.** Rules appear in two supporting places, and neither replaces it:

| Job | Done by | Why | Sprint |
|---|---|---|---|
| Deciding which accounts or transactions raise an alert | Rules engine and ML model (plain code) | This is how real banks do it. It is fast, cheap and easy to audit. An LLM would be slower, costlier and harder to audit | 5. Until then, alerts are built from the dataset's pattern files |
| Investigating an alert: deciding what to look at next, following the money, judging which pattern fits, explaining it with guidance, drafting the case | **LLM agent** | The next step depends on what the last step revealed, and the guidance is unstructured text | 1 to 4 |
| Lookups, arithmetic, and checking every cited transaction and quote | Ordinary code | These must be exact and never guessed | all |
| Approving the case | Human investigator | Accountability | 1 |
| Investigating the same alerts with no LLM, as a control group | Plain code ("deterministic pipeline") | To measure what the LLM actually adds | 4 |

### 12.2 The two terms, in plain words

- **Rules baseline** = a normal program of if-statements (amount over a threshold, many small transfers, money moving in a circle). Its job in this project is to *generate alerts* (Sprint 5), and it is the score the ML detection model has to beat. It is not the agent and it does not investigate anything.
- **No-LLM ablation** = an experiment. "Ablation" means removing one part of a system to see what gets worse. Here the part removed is the LLM. I build a second investigator out of plain code, run both investigators on the same frozen alerts, and compare the results. It is a measurement, not a feature of the product.

### 12.3 Why run this experiment

A fair skeptic says: "AML is mostly rules. Why not just if-statements?" The answer in this project has two halves.
1. For **detecting** suspicious activity, the skeptic is right, and the project follows that: the LLM never decides whether an alert fires.
2. For **investigating** an alert after it fires, an analyst has to follow counterparties, decide what happened, read guidance and write a case. Much of that could also be scripted for simple cases, so the project tests it instead of arguing it.

### 12.4 How the experiment works (Sprint 4)

1. **Build the deterministic pipeline.** Fixed graph queries around the seed account (neighbors, a bounded multi-hop trace), a rule-based pattern classifier (for example, one account sending to many in a short window means fan-out), and a templated narrative. It uses the same read-only data access and returns the same case format as the agent.
2. **Run both on the same frozen alerts.** Same alerts, same tools, same output schema.
3. **Compare** pattern accuracy, evidence coverage, false escalations on benign controls, narrative usefulness (judge plus human check), and cost and latency.
4. **Report what the LLM adds and what it costs**, by pattern type.

Fairness rules:
- Give the deterministic pipeline a real, time-boxed effort (for example one week). A deliberately weak control proves nothing.
- Develop and tune both only on dev alerts. Finish and freeze the deterministic pipeline before looking at either one's results on the evaluation alerts.
- Use one model for the agent in the comparison table (section 9).

### 12.5 What each outcome means

| Result | What you say |
|---|---|
| The agent is clearly better | The LLM earns its cost, here is by how much and on which patterns |
| The two are close on simple patterns (fan-out, fan-in) but the agent is better on messy ones (stack, random, gather-scatter) | Use rules for the easy cases and the LLM for the hard ones; this is the most useful finding |
| The deterministic pipeline matches the agent | The LLM adds little on this dataset, and the project still demonstrates the controls (read-only tools, human approval, audit log, verified citations) that any agent would need |

Every outcome is credible. A measured "it depends" is stronger than an unmeasured claim.

### 12.6 One-paragraph interview answer

"Detection should be rules and ML, and in this project it is. The LLM only starts after an alert exists, where the work is open-ended. I didn't just assert that was worth it. I built a plain-code investigator, ran both on the same [N] frozen alerts, and found that the LLM [improved pattern accuracy from X to Y on stack and random patterns, at Z times the cost / added little on simple patterns]."

---

## 13. Guidance corpus and jurisdictions

### What goes in the corpus
Public AML guidance describing typologies and red flags. Candidates to start with: FATF typology and red-flag reports, FinCEN advisories, and FINTRAC indicators and operational alerts. Wolfsberg publications and the FFIEC BSA/AML manual are worth checking, but I have not verified their current availability or terms. Record for each document: source URL, publication date, jurisdiction, license or terms.

### Storage and search
Everything lives in the Postgres you already run:
- Parse PDFs (Docling or similar), chunk along section boundaries with a little overlap, embed with a local model.
- One row per chunk: text, embedding, a full-text search column, and metadata (source, jurisdiction, date, section title, URL).
- Original files stay in a gitignored folder. Publish your ingestion script and a source list, not the documents.
- `retrieve_guidance(pattern, query, jurisdiction)` runs vector and keyword search, merges results, filters by jurisdiction (plus international FATF material), and returns top passages with IDs.

### Where an alert's jurisdiction comes from
The accounts file gives each bank a name, and I verified how those names relate to currencies (section 10, "Resolved data questions"). Proposed rule: **an alert's jurisdiction is the country of the seed account's bank**, derived from the bank ID:
- Name of the form "<Country> Bank #N" gives that country (Canada, UK, Germany, and so on). Countries without a guidance corpus fall back to international (FATF) material only.
- US-style name (about 39% of accounts) gives the United States. This is **inferred**, not documented by the dataset authors, but strongly supported: 81% of payments sent from these banks are in US dollars, and every country label matches its national currency.
- "Crytpo" (sic) banks give no national jurisdiction (their payments are 100% Bitcoin). Use international virtual-asset guidance only.

Limits to state in the README: 58 of the 370 pattern blocks touch a Canadian-labeled account, and only 39 of 370 blocks sit entirely in one country, so most alerts are cross-border and the seed-bank rule is a simplification.

### Making it work across institutions (honest scope)
It cannot work for all institutions, and the project must not claim that. Institutions differ in jurisdiction, internal policy, risk appetite and thresholds. The design should adapt instead:
- **Per-jurisdiction corpora.** Demonstrate two (US and Canada) and test that a Canadian case does not cite US-only guidance.
- **Pluggable internal policy.** A real bank would load its own procedures as a separate, private collection. The code would not change.
- **Config-driven rules and thresholds.**
- **Optional experiment: single-institution view.** Real institutions see only transactions that touch them. Add a mode in which the graph tools only return transactions with at least one party at the seed account's bank (counterparty details beyond that are hidden), run the dev alerts again, and report how much pattern accuracy and evidence coverage drop. This directly tests whether the agent depends on a view no real institution has. Add it after Sprint 4 if time allows.
- **State plainly** that it was tested on one synthetic dataset and two jurisdictions' public guidance, and that real use would need institution-specific policies, validation and compliance review.

### Hand-labeled sets
A small mapping from AMLworld pattern types to the guidance passages that describe them (partly your judgment, so document how you made it), used for recall@k.

---

## 14. Sprint plan

Estimates are rough guesses for part-time work: about 1-2 weeks per sprint. Adjust to your schedule. Every sprint ends with its **Verify** checks, then a tag, a CHANGELOG entry, and a fresh-clone test.

### Sprint 0: Foundation
**Build:** Repo, linting, pre-commit, CI skeleton, README stub. Convert `HI-Small_Trans.csv` to Parquet with DuckDB (explicit column names, string IDs, `tx_id` = row number). Load accounts, normalize bank IDs to integers for joins, and map each bank to a jurisdiction label (section 13). Parse patterns into tables, store the 1,968 labeled rows outside any pattern as `other_laundering`, and compute for each multi-row block the accounts that appear in no other block (seed-eligible). Seeded dev/eval alert generator. Docker Compose with Postgres. Investigate the 8 duplicate account numbers. Add `CLAUDE.md`, `docs/PRD.md` and `.env.example` (Appendix B).
**Done when:** `docker compose up` starts the stack and tests pass.
**Verify:**
- Golden-number tests assert the measured facts: 5,078,345 transactions, 5,177 labeled, 370 pattern blocks, 3,209 pattern rows, every pattern row matched to exactly one transaction, 43 single-row blocks, 1,968 labeled rows outside any pattern (all dated 09/01 to 09/10), 245 seed-eligible blocks, 30,470 bank IDs after integer normalization.
- Two conversion runs produce identical checksums.
- A fresh clone in a new folder starts the stack from scratch.
- A tool-query latency test reports p95 for neighbor lookups on the full table. Run it in the real Docker setup: if a bind mount from the Windows drive misses the 1 second target, move the Parquet files into a Docker named volume.
- The generated dev and eval sets share no pattern block.
- A test commit with a `Co-Authored-By` line is rejected, and a test commit containing an em dash is rejected (Appendix B).
- Every positive seed appears in exactly one pattern block and in no `other_laundering` row; every benign seed appears in no labeled row.
**Resume bullet:** none. This sprint does not merit one.

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

### Sprint 2: Audit trail and faithfulness
**Build:** Append-only audit log. OpenTelemetry traces into Postgres (Langfuse later, if memory allows). Programmatic citation verification. First measurements on the dev set.
**Done when:** Any case can be reconstructed from the log, and faithfulness is measured over the dev alerts.
**Verify:**
- Rebuild one case's full timeline from the audit log alone and compare it with the live run.
- `UPDATE` and `DELETE` on the audit table are blocked.
- Corrupt good cases on purpose (change one amount, ID, date or party): the verifier must flag every corruption and raise no false alarms on clean cases.
**Resume bullet template:**
> Added an append-only audit log, distributed tracing and automated citation verification; drafted narratives cited fully verified transactions in [X]% of [N] cases.

### Sprint 3: RAG over AML guidance
**Build:** Corpus ingestion and chunking with jurisdiction tags. pgvector plus full-text hybrid search with local embeddings. `retrieve_guidance` MCP tool. Citation validation. Hand-labeled pattern-to-guidance set.
**Done when:** Narratives cite guidance passages, citations validate against the index, and recall@k is reported.
**Verify:**
- Spot-check about 20 chunks against the source PDFs, especially tables and headers.
- Compare keyword-only, vector-only and hybrid retrieval on the labeled set. Hybrid should be at least as good as either; if not, investigate.
- Alter a quoted span and confirm it is caught.
- Run a Canadian case and a US case and confirm no jurisdiction leakage.
- Query something unrelated and confirm "no guidance found".
**Resume bullet template:**
> Implemented hybrid-search RAG over public AML typology guidance with jurisdiction filtering, exposed through an MCP tool, with citation validation; retrieval recall@[k] of [X] on a hand-labeled set of [N] queries.

### Sprint 4: Evaluation, ablation and final run
**Build:** pytest eval harness. GitHub Actions gates that run on deterministic checks and recorded fixtures only. The deterministic no-LLM pipeline and the ablation (section 12). A judge model validated against a small human-labeled set. Written failure analysis. **Freeze, tag, then run the frozen evaluation set on the report-tier model** (uncached, one model per table), and report dev-tier and report-tier results side by side.
**Done when:** A pull request fails CI if faithfulness, retrieval or latency regresses, and the final results table exists.
**Verify:**
- Break it on purpose (bad prompt, retrieval k=1, tiny tool budget) and confirm CI fails; confirm the real version passes.
- Label 30-50 narratives yourself and report judge agreement.
- Repeat a run 3-5 times, if quota allows, to see run-to-run spread, and set thresholds outside the noise.
- Confirm the evaluation set was not used for any prompt change since the freeze tag.
- Confirm the deterministic pipeline got a fair, time-boxed effort and was frozen before its evaluation results were looked at.
**Resume bullet templates:**
> Built a CI evaluation harness gating on citation faithfulness, retrieval quality and latency, with an LLM judge calibrated to [X]% agreement with human labels.
> Ablation: compared the agent against a deterministic pipeline on [N] frozen alerts; the agent improved pattern accuracy from [X]% to [Y]% at [Z]x the cost.

### Sprint 5: Rules-based alerting and detection model
**Build:** Config-driven rules engine (amount thresholds, structuring, velocity, cycles). Graph features and a baseline classifier (scikit-learn, optionally XGBoost). Chronological 60/20/20 train/validation/test split by timestamp, as the dataset authors recommend, on the 09/01 to 09/10 primary period (HI-Small cutoffs: 2022/09/06 13:36 and 2022/09/08 16:12; recompute in Sprint 0 after sorting by timestamp). Rows dated after 09/10 are excluded from train, validation and test and reported separately (decision in section 10); watch for patterns that start before a cutoff and finish after it. Class-imbalance handling. Report with and without the payment-format feature, and on all labeled rows versus pattern rows only. Replace pattern-file alerts with generated alerts.
**Done when:** The full pipeline runs on generated alerts, with detection metrics and end-to-end results reported.
**Verify:**
- Train, validation and test do not overlap in time, and no feature uses information from after the row's own timestamp. (Accounts naturally appear in several splits; that is how this benchmark is used.)
- Shuffle the labels and retrain; the score must fall to near chance.
- The model beats a majority-class baseline and the rules baseline.
- Report PR-AUC against the base rate, not accuracy.
- Re-score without the payment-format feature and report the drop (nearly all labeled laundering is ACH).
**Resume bullet template:**
> Built a graph-feature detection model (PR-AUC [X] vs a rules baseline of [Y]) that feeds the investigation agent; evaluated the pipeline end to end on [N] generated alerts.

### Sprint 6: Hardening
**Build:** Prompt-injection test suite (AgentDojo-style cases) against tool outputs, using an added and disclosed synthetic text field. Optional smolagents analysis step in a locked-down Docker sandbox. Generated model card per agent (purpose, risk rating, data lineage, test results).
**Done when:** Injection tests run in CI and results are reported before and after defenses.
**Verify:**
- Run the injection suite before and after defenses.
- Attempt an injected tool call outside the allowlist; it must be blocked.
- If the sandbox exists, try network access from inside it; it must fail.
- Diff the generated model card against the real configuration.
**Resume bullet template:**
> Red-teamed the agent with [N] prompt-injection cases, reducing attack success from [X]% to [Y]%, and generated per-agent model cards documenting controls and test results.

### Habits that apply to every sprint
- **Test the checkers.** The verifiers are code too. The deliberate-corruption test is how you know they work.
- **Keep a claims ledger.** For every resume bullet, note the test, metric or file that proves it. No evidence, no bullet.
- **Run the fresh-clone test at every tag**, ideally with a friend following only your README.
- **Compare against baselines** wherever it makes sense.
- **No AI co-author lines and no em dashes**, in every commit and file (Appendix B).

---

## 15. Repository layout (suggested)

```
aml-investigation-agent/
├── README.md                 # architecture, results, limitations, threat model
├── CLAUDE.md                 # instructions for Claude Code (Appendix B)
├── .env.example              # AML_DATA_DIR and other settings, no secrets
├── docker-compose.yml
├── pyproject.toml
├── .github/workflows/        # lint, test, eval gates (deterministic only)
├── data/                     # gitignored; download notes + checksums, Parquet output
├── scripts/                  # convert to Parquet, build alert sets, ingest guidance
├── services/
│   ├── api/                  # FastAPI: cases, review
│   ├── agent/                # LangGraph workflow, state, prompts
│   ├── mcp_graph/            # read-only graph tools
│   └── mcp_guidance/         # retrieval tool (Sprint 3)
├── aml_agent/
│   ├── schemas/              # Pydantic models (alert, case, evidence)
│   ├── llm/                  # provider interface, model config, response cache
│   ├── verify/               # faithfulness and citation checks
│   ├── retrieval/            # chunking, embeddings, hybrid search
│   ├── baseline/             # no-LLM comparison pipeline (Sprint 4), rules-based alerting (Sprint 5)
│   └── detection/            # features and model (Sprint 5)
├── evals/
│   ├── alerts/               # versioned dev and frozen eval alert sets
│   ├── labels/               # human-labeled sets
│   ├── fixtures/             # recorded model responses for CI
│   ├── runs/                 # run manifests and results per model tier
│   └── run_evals.py
├── docs/
│   ├── PRD.md                # this document
│   ├── sprints/              # one file per sprint, extracted from section 14
│   ├── architecture.md
│   ├── threat_model.md
│   ├── decisions/            # short architecture decision records
│   └── model_cards/          # generated (Sprint 6)
└── CHANGELOG.md              # one entry per sprint tag
```

---

## 16. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Looks like a data science project rather than an AI-developer project | Build the controls (MCP, approval, audit, citations) first; the detection model comes late (Sprint 5) |
| "Why use an LLM when rules work?" | Rules do the alerting; the LLM does the investigating; the no-LLM comparison (section 12) answers it with measurements |
| Agent only summarizes | Seed-only alerts force discovery; step budgets; evaluate evidence coverage and pattern accuracy, not just prose |
| Free-tier quota runs out mid-evaluation | Dev tier on a low-usage model, response caching, run manifests that resume, measure tokens early, optional second provider reported as a separate model |
| Cheaper dev model behaves differently from the report model | Bake-off in Sprint 1, freeze before the final run, report both tiers |
| Cloud model retired or renamed | Model tag in config; record the tag and date in every report |
| Prompts leave the machine | Synthetic and public data only; never send private material |
| 16 GB RAM pressure | DuckDB/Parquet, HI-Small only, Docker memory cap, Langfuse last |
| Dataset quirks (no tx ID, duplicate headers, inconsistent zero-padding of bank IDs, duplicate account numbers, non-unique bank names) | Explicit schema in Sprint 0, integer bank-ID joins, golden-number tests |
| Pattern accounts shared across blocks make ground truth ambiguous | Seed must appear in exactly one block (245 of 327 blocks qualify) |
| Label leakage (nearly all laundering is ACH; rows after 09/10 are 59% laundering) | Report with and without payment format; score post-09/10 rows separately; chronological split on the primary period |
| Labeled "Other" laundering rows outside any pattern | Stored separately; never used as pattern ground truth; reported separately in Sprint 5 |
| 43 single-row pattern blocks | Degree-1 patterns by generator design; excluded from alerts |
| Jurisdiction derived by inference | Rule documented; the US label is supported by currency evidence but not documented by the dataset authors; state the limitation |
| Synthetic-data results oversold | Explicit limitations section; never claim real-world performance |
| Retrieval corpus licensing | Check terms per source; link to originals; store only what you may |
| Dataset license (CDLA-Sharing 1.0) | Do not publish the data or bulk extracts; commit code, row-number IDs and results; license notice on any fixtures; cite the authors |
| Agent sees every bank's transactions, unlike a real institution | State it as a limitation; optional single-institution-view experiment (section 13) |
| Injection tests irrelevant because the data has no free text | Add and disclose a synthetic text field in Sprint 6 |
| Code-executing agent is a security risk | Optional only; Docker sandbox, no network, read-only data |
| Scope creep | Sprints 5 and 6 are optional; ship a polished Sprint 3 or 4 first |
| Langfuse self-hosting is heavier than expected | Postgres trace store is the default; add Langfuse last |

---

## 17. Resume and interview guidance

### Resume rules
- Write a bullet only **after** you have the number. Replace every `[X]` with a measured value or delete the claim.
- Use the project's actual scope: "synthetic AML investigation agent," not "AML system."
- Lead with the engineering: MCP tool layer, checkpointed human approval, audit trail, verified citations, CI evaluation gates.

### A short project blurb
> AML Investigation Agent: an agentic AML investigation assistant over IBM's synthetic AMLworld transactions. LangGraph workflow with a read-only MCP tool layer, hybrid-search RAG over public AML guidance with jurisdiction filtering, human approval checkpoints, append-only audit logging, verified citations, and CI evaluation gates, plus an ablation against a deterministic pipeline. Runs locally in Docker Compose using free-tier models.

### Questions to be ready for
1. Why a human approval step, and what exactly does the human see?
2. How do you know the agent isn't hallucinating transactions? (programmatic verification, and how you tested the verifier)
3. AML is mostly rules. Why use an LLM at all? (section 12 and the ablation result)
4. What happens with prompt injection in tool outputs?
5. How would this change with real data, real volumes and a real model risk process? (E-23 / SR 11-7 thinking, third-party model controls)
6. You developed on one model and reported on another. How did you keep that honest? (section 9)
7. Does it work for other institutions or jurisdictions? (section 13)
8. How would you port this to Azure AI Foundry? (mapping table in section 8)
9. What did the failure analysis show?

### Honest limitations to volunteer
Synthetic data; free-tier model limits; simulated alert source in Sprints 1-4; US jurisdiction inferred from bank names and currencies; no real-time scale; no regulatory validation; tested on one dataset.

---

## 18. Open questions

- Which public guidance documents will you include, and what are their terms of use?
- Do you want a minimal review UI, or is an API plus CLI enough?
- Which models can your free Ollama account actually run? Check this before the Sprint 1 bake-off.
- Do you accept the case-jurisdiction rule in section 13 (seed account's bank)?

Resolved: hardware (16 GB RAM, integrated GPU, no local LLM), dataset location and contents, free-text field (none), model approach (dev model first, better model for reporting), project name, project folder, how to treat rows dated after 09/10, the 1,968 "Other" laundering rows, the 43 single-row blocks, and the bank-name pool.

---

## 19. References

Company and market context
- Citi, Introducing AI Agents (Arc): https://www.citigroup.com/global/news/perspectives/2026/introducing-ai-agents-next-phase-citi-artificial-intelligence-journey
- Manulife and Microsoft partnership (Agent 365): https://news.microsoft.com/source/canada/2026/07/22/manulife-expands-partnership-with-microsoft-to-accelerate-enterprise-ai-governance-and-innovation/
- Manulife selects Akka for its agentic platform: https://akka.io/blog/manulife-selects-akka-to-operationalize-agentic-ai
- Deloitte and HPE (CFO Insights on Zora AI): https://www.deloitte.com/us/en/services/consulting/articles/hpe-agentic-ai-collaboration.html
- Goldman Sachs and Anthropic agents (reporting via Sharecast/CNBC): https://www.hl.co.uk/shares/stock-market-news/company--news/goldman-sachs-working-with-anthropic-to-automate-accounting,-compliance-roles

Job postings referenced (check what is currently open)
- Deloitte Senior AI Engineer (Platforms): https://usijobs.deloitte.com/en_US/careersUSI/JobDetail/USI-EH26-MF-UK-GEN-AI-Platform-Manager-Hyderabad/325796
- Deloitte AI/ML Senior Consultant: https://southasiacareers.deloitte.com/job/Bengaluru-T&T-EAD-AI&Data-Senior-Consultant-AI-ML-Bengaluru/55355544/
- Manulife AI Engineer (GenAI/LLMOps): https://builtintoronto.com/job/ai-engineer-genai-llmops/8544236
- Bank of America AI Monitoring & Control: https://careers.bankofamerica.com/en-us/job-detail/26032896/senior-engineer-ai-monitoring-control-capabilities-multiple-locations
- Bank agentic AI engineer (MCP, guardrails): https://jobs.dou.ua/companies/fuib/vacancies/367416/
- AI Engineer, Traded Risk: https://www.iagora.com/work/en/offer/job-india-engineering/6426486

Regulation
- OSFI Guideline E-23, Model Risk Management (2027), effective May 1, 2027: https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-e-23-model-risk-management-2027-letter
  (E-23 does not name agents explicitly; applying it to agents is an interpretation.)

Data and benchmarks
- IBM AMLworld paper (IBM Research and ETH Zurich): https://research.ibm.com/publications/realistic-synthetic-financial-transactions-for-anti-money-laundering-models
- Paper on arXiv: https://arxiv.org/pdf/2306.16424
- NeurIPS 2023 supplement (Table 4 dataset sizes, Table 8 pattern vs "Other" laundering, license and intended use): https://papers.neurips.cc/paper_files/paper/2023/file/5f38404edff6f3f642d6fa5892479c42-Supplemental-Datasets_and_Benchmarks.pdf
- Kaggle dataset page (text read from your paste; dataset table, license, split advice): https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml
- AMLSim (source of the 8 pattern types, per the Kaggle page): http://github.com/IBM/AMLSim
- Community Data License Agreement, Sharing, Version 1.0 (read the full text before publishing anything derived from the data): https://cdla.dev
- AgentDojo (NeurIPS 2024): https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract.html

Models and providers
- Ollama cloud plans and limits: https://registry.ollama.ai/cloud
- Ollama cloud model usage levels (community guide, verify): https://github.com/RedBeret/awesome-ollama-models
- Gemma 4 31B vs Qwen comparison (vendor-reported scores): https://regolo.ai/gemma-4-31b-vs-qwen3-6-35b-a3b-when-to-use-which/
- Gemma 4 31B vs GPT-OSS 120B (aggregator, low confidence): https://benchlm.ai/compare/gemma-4-31b-vs-gpt-oss-120b
- Gemini API Additional Terms of Service (unpaid services data use): https://ai.google.dev/gemini-api/terms_preview

Caveat on sources: several market and model claims come from secondary or aggregator sources, and job postings and free-tier limits change. Verify before quoting any figure publicly.

---

## Appendix A: Measured facts about your HI-Small files

Measured October 2026 on `HI-Small_Trans.csv`, `HI-Small_accounts.csv` and `HI-Small_Patterns.txt` in your dataset folder. Sprint 0 turns these into automated golden-number tests. "Documented" means also stated in the paper or supplement.

| Fact | Value |
|---|---|
| Transactions | 5,078,345 |
| Accounts in accounts file | 518,573 unique account numbers (8 duplicates); 515,088 distinct (bank, account) pairs appear in transactions |
| Bank IDs | 30,470 distinct. The transactions file zero-pads them inconsistently (58 banks appear under two spellings, for example `010` and `0010`); the accounts file has no padding. Join on the integer value. No account is split by this |
| Transactions labeled laundering | 5,177 (about 1 per 981) |
| Time span | 2022/09/01 00:00 to 2022/09/18 16:18, minute resolution, no time zone. Documented: the Small datasets span 10 days |
| Background period | 09/01 to 09/10: 207K to 1.1M rows per day |
| Tail period | 09/11 to 09/18: 1,108 rows (396 on 09/11 falling to 11 on 09/18); 655 labeled laundering (59%), 453 unlabeled and all ACH. The Kaggle page says post-period transactions are "all laundering" (user report); not exactly true here |
| Row order | Not sorted by timestamp. Chronological 60% / 80% cutoffs: 2022/09/06 13:36 and 2022/09/08 16:12 (over all rows) |
| Kaggle dataset table (HI-Small) | Sep 1 to 10, 10 days, 515K accounts, 5M transactions, 5.1K laundering, 1 per 981 |
| License | CDLA-Sharing 1.0 (Kaggle page) |
| Transactions file columns | Timestamp, From Bank, Account, To Bank, Account, Amount Received, Receiving Currency, Amount Paid, Payment Currency, Payment Format, Is Laundering (the two `Account` columns share a name) |
| Accounts file columns | Bank Name, Bank ID, Account Number, Entity ID, Entity Name |
| Free-text field | None |
| Transaction ID | None (use row number) |
| Payment formats | Cheque 1,864,331; Credit Card 1,323,324; ACH 600,797; Reinvestment 481,056; Cash 490,891; Wire 171,855; Bitcoin 146,091 |
| Payment format of pattern rows | 3,208 ACH and 1 Bitcoin |
| Largest currencies by count | US Dollar 1,879,341; Euro 1,172,017; Swiss Franc 237,884; Yuan 206,551; Shekel 194,988; Rupee 192,065 |
| Self-transfers (same bank and account) | 591,212 |
| Pattern blocks | 370 (FAN-OUT 48, CYCLE 54, GATHER-SCATTER 51, STACK 43, RANDOM 41, BIPARTITE 49, FAN-IN 40, SCATTER-GATHER 44) |
| Pattern rows | 3,209, each matching exactly one labeled transaction |
| Pattern headers | Carry generator parameters, for example "Max 16-degree Fan-Out" |
| Single-row blocks | 43 (FAN-OUT 8, RANDOM 13, BIPARTITE 18, FAN-IN 4): degree-1 patterns by generator parameter |
| Multi-row blocks | 327 (FAN-OUT 40, CYCLE 54, GATHER-SCATTER 51, STACK 43, RANDOM 28, BIPARTITE 31, FAN-IN 36, SCATTER-GATHER 44) |
| Block size | 1 to 32 transactions, median 7; median 8 accounts per block |
| Pattern accounts | 3,170; 100 appear in more than one block; 138 of 327 multi-row blocks share an account with another block |
| Seed-eligible blocks (an account in no other block) | 245 of 327: BIPARTITE 28, CYCLE 40, FAN-IN 29, FAN-OUT 32, GATHER-SCATTER 33, RANDOM 24, SCATTER-GATHER 30, STACK 29 (the "no other labeled row" check is still to do in Sprint 0) |
| Labeled rows outside any pattern ("Other" laundering) | 1,968, all dated 09/01 to 09/10; only 42 touch a pattern account; 25 have a sender that earlier received a labeled row |
| Structure of those 1,968 | 1,297 groups: 1,238 isolated single transfers (1,187 ACH, 31 Bitcoin, 20 Cheque); 59 larger groups, the largest with 247 rows (5 senders to 238 receivers) |
| Labeled rows that are ACH | At least 4,395 of 5,177 (3,208 pattern plus 1,187 isolated "Other") |
| Bank names | "<Label> Bank #N" for 33 labels (about 61% of accounts); the other 201,078 accounts (about 39%) use 468 US-style names shared by 10,885 bank IDs. Each bank ID has one name |
| Currency of payments sent, by bank label | US-style names: US Dollar 81%. Canada: Canadian Dollar 91%. UK: UK Pound 88%. Germany: Euro 98%. Switzerland: Swiss Franc 96%. Japan: Yen 85%. "Crytpo" (sic): Bitcoin 100% |
| Blocks entirely within one country | 39 of 370 |
| Blocks touching a Canadian-labeled account | 58 of 370 |
| Other files in your folder | HI/LI Medium and Large, LI-Small. Not used. The Large transaction files are about 17 GB each |

---

## Appendix B: Building with Claude Code

### Where things live
- **Repo:** `D:\Coding\AI_Agents\aml-investigation-agent`. The raw dataset stays in `D:\Coding\AI_Agents\archive`, outside the repo. Point to it with `AML_DATA_DIR` in a gitignored `.env`, and commit `.env.example`.
- **Docker on Windows.** Use Docker Desktop with the WSL2 backend, as in section 6. Bind mounts from a Windows drive can be slow for file-heavy work. Do not decide in advance: the Sprint 0 latency test shows whether the repo-folder mount is fast enough, and the fallback is a Docker named volume for the Parquet files.
- **Which shell.** Claude Code can run in Windows or in WSL. Either works with the repo on D:. If you use WSL, files under `/mnt/d` are slower to read than files in the WSL filesystem, so measure again rather than assuming.

### Before you start

**Installed and configured**
- Claude Code.
- git, with your identity set (`git config --global user.name "Your Name"` and `git config --global user.email "you@example.com"`), so commits carry only you.
- Python 3.11 or newer.
- Docker Desktop with the WSL2 backend.
- pre-commit (`pip install pre-commit`).
- A GitHub account and an empty private repository, for the CI skeleton.

**Docker memory cap.** Create `%UserProfile%\.wslconfig` containing the following, then run `wsl --shutdown` and restart Docker Desktop. Use 6GB if Windows feels slow.
```
[wsl2]
memory=8GB
```

**Dataset access.** The data stays in `D:\Coding\AI_Agents\archive`, outside the repo. Start Claude Code from the repo with `claude --add-dir D:\Coding\AI_Agents\archive` (inside a session, `/add-dir` does the same). This grants edit access as well as read access, so as a safety net mark the three HI-Small files as read-only in Windows file properties. `CLAUDE.md` already tells Claude Code to use only those three files.

**Start in plan mode.** Run `claude --permission-mode plan` (or press Shift+Tab in a session to switch modes) before pasting the Sprint 0 prompt.

**Files to place in the repo**

| File | Location |
|---|---|
| `CLAUDE.md` | repo root |
| This PRD | `docs/PRD.md` |
| `settings.json` (provided separately) | `.claude/settings.json` |

**Not needed yet.** Ollama and a cloud model (Sprint 1), guidance PDFs (Sprint 3), and any API key. Never put a key in the repo.

### One-time setup
1. `git init` in the repo folder. Add a `.gitignore` for `data/`, `*.parquet`, `*.duckdb`, `.env`, and local caches.
2. Put this document at `docs/PRD.md`, `CLAUDE.md` at the repo root, and the provided `settings.json` at `.claude/settings.json`.
3. Ask Claude Code to split section 14 into `docs/sprints/sprint-0.md` through `sprint-6.md`, unchanged, so each session reads one sprint instead of the whole PRD.
4. Commit that as the first commit.

### Working loop for every sprint
1. Start in plan mode with the sprint file. Read the plan and fix it before any code is written.
2. Write tests first for the data layer and for every verifier. Implement in small steps with a commit after each.
3. **You run the sprint's Verify checks yourself.** "All tests pass" from the tool is not the same as the Verify list. The deliberate-corruption test, the kill-and-resume test and the read-only test matter most.
4. Update `CHANGELOG.md`, tag the release, and do a fresh-clone test.
5. Add any new resume bullet to your claims ledger together with the test or metric that proves it.

### Mistakes to watch for
- Loading the whole CSV into pandas. `CLAUDE.md` forbids it.
- "Fixing" a failing golden-number test by editing the expected number. The rule is that golden numbers change only when you say so.
- Verifier tests that mock the very data they are meant to check. Verifier tests should run against real Parquet slices.
- Writing results into the README or resume before they are measured.
- Adding services early (for example Langfuse) or unrequested dependencies.
- Prompt changes made after looking at the evaluation set.
- A commit message that ends with a `Co-Authored-By` or "Generated with Claude Code" line, or text containing an em dash. See the next subsection.

### Commit and writing rules, with enforcement

Two rules apply everywhere in the repo:
1. **No AI co-author.** Commits and pull request descriptions never list Claude as a co-author and never contain "Co-Authored-By" or "Generated with Claude Code" lines. Commits carry your git identity only.
2. **No em dashes.** The em dash character never appears in code, comments, docstrings, documentation, test names, strings, commit messages, pull request text, the agent's prompts, or the agent's generated case narratives. Use commas, periods, colons or parentheses instead.

Instructions alone are not reliable here: Claude Code adds attribution by default, and public bug reports describe the attribution setting being ignored in some versions (for example when a commit goes through a built-in commit skill). So enforce it three ways:

- **Project setting.** In `.claude/settings.json` (commit it to the repo), turn the attribution off. The Claude Code settings reference lists `attribution.commit` and `attribution.pr` (and `attribution.sessionUrl`, for cloud and Remote Control commits), and marks the older `includeCoAuthoredBy` as deprecated. A public bug report quotes the documentation as saying an empty string hides the attribution; I could not read that exact entry myself, and the same report says the setting was ignored in one version. So treat the setting as a first layer and test it in Sprint 0:
```json
{
  "attribution": {
    "commit": "",
    "pr": ""
  }
}
```
- **Git hooks.** The settings can fail silently, so add hooks that reject a bad commit. In `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: local
    hooks:
      - id: no-em-dash
        name: no em dashes anywhere
        language: pygrep
        entry: "\u2014"
        types: [text]
      - id: no-ai-coauthor
        name: no AI co-author or generator line in commit messages
        language: pygrep
        entry: '(?i)^co-authored-by:|^claude-session:|generated with \[?claude|claude\.ai/code/session'
        stages: [commit-msg]
```
  Install both hook types once with `pre-commit install` and `pre-commit install --hook-type commit-msg`. The em dash is written as the escape `\u2014` so the config file itself stays clean.
- **A test for the agent's own text.** A unit test over the recorded fixtures fails if any generated case narrative contains an em dash, and the agent's prompts tell it not to use one.

Prove the hooks work in Sprint 0 (see its Verify list). A rule that has never been seen to fail a bad commit is not a control.

### Sprint 0 kickoff prompt (paste into Claude Code, in plan mode)
```
Read CLAUDE.md and docs/PRD.md (sections 5, 10 and 14, and Appendix A).
We are doing Sprint 0 only. Plan first and wait for my approval before writing code.

Deliver, stopping after each numbered item to show me the test output:
1. Repo scaffolding: pyproject.toml, ruff, pytest, pre-commit (including the two
   local hooks and the .claude/settings.json attribution setting from Appendix B),
   .gitignore, .env.example (AML_DATA_DIR), Makefile.
2. scripts/convert_to_parquet.py using DuckDB: explicit column names
   (from_account, to_account), string IDs, tx_id = 1-based original row number,
   Parquet output under data/. Never load the CSV into pandas.
3. Loaders for the accounts file (bank ID normalized to an integer) and the
   patterns file (parse blocks and header parameters, match each pattern row
   to exactly one tx_id).
4. Tables: other_laundering (labeled rows outside any pattern) and seed-eligible
   accounts per multi-row block.
5. tests/golden/ asserting every number in Appendix A.
6. Seeded alert generator: seed rule, window matching for benign controls,
   dev/eval split with no shared pattern block.
7. docker-compose.yml with Postgres + pgvector.
8. A tool-query latency test (p95 for neighbor lookups on the full table).

Then prove the hooks work: attempt one commit whose message has a Co-Authored-By
line and one commit containing a file with an em dash. Both must be rejected.
Show me the output. Never put Claude as co-author and never use em dashes.

If any measured number differs from Appendix A, stop and tell me. Do not change
the expected number to make a test pass.
```
