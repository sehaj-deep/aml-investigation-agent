# Sprint 2 Verify results

Run 2026-10-14. Model: **scripted provider only**; faithfulness over dev alerts with a live model is not measured yet.

| Verify item | Result | Evidence |
|---|---|---|
| Rebuild one case's full timeline from the audit log alone and compare with the live run | Yes: the state rebuilt from Postgres audit events equals the Postgres checkpoint of the live run exactly (a case with a "request more" round and an approval); the timeline lists every event; the hash chain verifies | `tests/docker/test_audit_postgres.py`, `tests/unit/test_audit.py` |
| UPDATE and DELETE on the audit table are blocked | Yes: both raise "audit_log is append-only"; TRUNCATE also blocked; row count unchanged | `tests/docker/test_audit_postgres.py` |
| Corrupt good cases on purpose: every corruption flagged, no false alarms on clean cases | Yes: 24 clean cases built from the real Parquet rows of the dev positive blocks raise no warnings; all 288 corruptions (12 kinds: amount by 1 and by 0.01, currency, invented tx_id, swapped tx_id, timestamp by 1 minute and by 1 day, each party field, an invented cited ID) are flagged with the right field | `tests/golden/test_verifier_corruption.py` |
| Faithfulness measured over the dev alerts | **Not done**: needs a live model. Harness ready: `python evals/run_evals.py --set dev` | |

Also: traces for every case, node, model call and tool call are stored in the Postgres `traces` table; a case run through the Docker stack is verified (`faithful`, `grounded`) and its timeline is served at `GET /cases/{id}/timeline`.
