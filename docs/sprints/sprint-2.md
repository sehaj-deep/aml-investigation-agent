### Sprint 2: Audit trail and faithfulness
**Build:** Append-only audit log. OpenTelemetry traces into Postgres (Langfuse later, if memory allows). Programmatic citation verification. First measurements on the dev set.
**Done when:** Any case can be reconstructed from the log, and faithfulness is measured over the dev alerts.
**Verify:**
- Rebuild one case's full timeline from the audit log alone and compare it with the live run.
- `UPDATE` and `DELETE` on the audit table are blocked.
- Corrupt good cases on purpose (change one amount, ID, date or party): the verifier must flag every corruption and raise no false alarms on clean cases.
**Resume bullet template:**
> Added an append-only audit log, distributed tracing and automated citation verification; drafted narratives cited fully verified transactions in [X]% of [N] cases.
