# Claims ledger

Every claim used on a resume or in an interview, with the file or test that proves it. All results are on IBM's synthetic AMLworld data.

| Claim | Proof |
|---|---|
| Agentic AML investigation platform: LangGraph agent with read-only MCP tools, human decisions under a server-enforced four-eyes rule, tamper-evident audit log | `README.md`; `docs/decisions/0008`, `0009`, `0015`; `tests/unit/test_agent_graph.py`, `tests/docker/test_worker_api.py::test_kill_worker_while_paused_then_resume`, `tests/docker/test_audit_postgres.py` |
| On 150 frozen alerts the agent escalated laundering twice as often as false alarms (49% vs 25%) and closed 33% of laundering, a measured reason every case keeps a human decision | `docs/findings/2026-10-15-final-evaluation.md`; `evals/runs/triage/triage-ollama-20261015T065057Z.json`; tag `eval-freeze` |
| Supporting evidence verified against source data in 150 of 150 evaluated cases; the citation verifier caught 288 of 288 injected corruptions with no false alarms on 24 clean cases | final evaluation file above; `tests/golden/test_verifier_corruption.py`; `docs/decisions/0009` |
| Verbatim check on RAG citations dropped 94 of 280 non-verbatim guidance quotes | final evaluation file above; `tests/unit/test_guidance.py` |
| Hybrid RAG (pgvector plus full-text, reciprocal rank fusion): right document first 88.9% vs 77.8% keyword-only | `docs/SCORECARD.md` part E; `evals/runs/guidance/`; `evals/guidance_eval.py` |
| XGBoost transaction monitoring on IBM's benchmark split: F1 71.2% vs 63.2% best in the IBM paper; 50.6% without the simulator's shortcuts | `docs/SCORECARD.md` part A; `evals/runs/detection/model-20261014T235452Z.json`; `docs/model_cards/detection-model.md` |
| Alert policy catches 89% of laundering accounts at a 94% false-alarm rate, with below-the-line testing | `docs/decisions/0014-alert-queue-and-alert-policy.md`; same detection run |
| Controlled prompt change raised tool use from 0.08 to 2.25 lookups per case and cut missed laundering on a development set | `docs/findings/2026-10-14-tool-lookups.md` |
| Prompt-injection controls: a model obeying injected instructions cannot write, finalize or cite unverified data; live spot check refused takeover, prompt-leak and fake-evidence attacks | `docs/findings/2026-10-15-prompt-injection.md`; `tests/unit/test_injection.py`; `evals/runs/redteam/` |
| Investigator copilot with streamed tool steps and checked citations; SAR draft with checked facts and four-eyes approval | `docs/decisions/0016`, `0017`; `tests/unit/test_copilot.py`, `tests/unit/test_sar.py`, `tests/docker/test_worker_api.py` |
| Public demo on a free tier: single container, reviewed cases, live AI with per-visitor and daily limits | https://aml-investigation-agent.onrender.com; `deploy/space/`; `tests/docker/test_demo_limits.py` |
