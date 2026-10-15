# Finding: final evaluation of the AI analyst (frozen, 150 monitoring alerts)

Date: 2026-10-15. Model: gpt-oss:20b (Ollama cloud). Prompt p10. Code frozen at tag `eval-freeze` (commit 2ef2e91). Result: `evals/runs/triage/triage-ollama-20261015T065057Z.json`.

## Set-up

- **Alerts:** the evaluation sample of the monitoring queue, 50 per priority band, seeded and never used for tuning. 55 are laundering accounts and 95 false alarms.
- **Run:** the AI review ran end to end on each alert, up to the analyst's decision, one pass.
- **Server errors:** nine cases failed with Ollama server errors (HTTP 500) and were run again on the frozen code (`evals/runs/triage/retried-after-server-errors.json`). Twice the run stopped waiting on a model reply that never came; it resumed from its saved progress, since no completed case is lost or repeated.

## Results

| AI recommendation | Laundering (55) | False alarms (95) |
|---|---|---|
| Escalate | 49.1% | 25.3% |
| Needs more information | 18.2% | 38.9% |
| Close | 32.7% | 35.8% |

**By priority band** (laundering cases):

| Band | Laundering cases | Escalated | Closed |
|---|---|---|---|
| High | 46 | 54.3% | 32.6% |
| Medium | 7 | 14.3% | 42.9% |
| Low | 2 | 1 of 2 | 0 of 2 |

**Faithfulness:**
- Every supporting transaction verified against the source data in 150 of 150 cases.
- 149 of 150 drafts were valid; one malformed draft was routed to human review.
- The review cited guidance in 71% of cases. Of 280 guidance quotes, 186 matched their passage word for word and were kept; 94 did not and were dropped and reported.

**Cost:** 3.7 million tokens in total (about 21% of the free Ollama quota). Per case, the median was 22,150 tokens, 49 seconds (p95 119 seconds) and 2 tool calls.

## Reading

- **Escalation carries a signal:** the AI escalates laundering about twice as often as false alarms.
- **Its "close" carries almost none:** it closes laundering about as often as false alarms. Acting alone, it would have missed a third of the laundering in this sample. The product requires a recorded human decision on every case, and this result is the measured reason why.
- **"Needs more information" is common,** so a human sees most cases either way. The AI's value here is the prepared evidence, network and narrative, not autonomous triage.
- **The grounding controls hold at scale.** No unverified evidence reached a reviewer. The word-for-word quote check was necessary: a third of the model's guidance quotes were not verbatim.

## Limits

One model, one pass, synthetic data. Medium and low bands contain few laundering cases (7 and 2), so their rates are not reliable. No analyst-time study was run.
