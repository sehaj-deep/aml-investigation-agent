# Scorecard

One fixed yardstick for every change. Each part names its question, test set and metrics; results are reported in this format, with caveats, before any interpretation. All data is synthetic (IBM AMLworld HI-Small); no result here shows real-world performance.

## A. Detection: does the risk score find laundering among ordinary accounts?

**Test set.** Every account active in a review period, at the data's natural laundering rate. Positive: the account sends or receives any labeled laundering transaction in the period (pattern or other laundering). Accounts of the frozen evaluation set (alert seeds and every account of its pattern blocks) are removed. Primary period only; payment format never used.

**Metrics.** Base rate; for each risk-score threshold: alerts raised, recall, precision, alerts per true case; average precision (PR-AUC) against the base rate. Also transaction-level minority-class F1 on the late test period, the metric used by the dataset paper.

**How to run.** `python evals/detection_eval.py` (no model, no quota; about a minute). Results: `evals/runs/detection/`.

**Results (2026-10-14, rules R1 to R6, `docs/decisions/0011-risk-indicators.md`)**

| Review period | Accounts | Positive | Base rate | PR-AUC (case score) | PR-AUC (subject only) |
|---|---|---|---|---|---|
| Sep 4 to 6 | 243,776 | 1,749 | 0.72% | 0.069 | 0.037 |
| Sep 7 to 9 | 360,360 | 1,964 | 0.55% | 0.076 | 0.040 |

Sep 7 to 9 by threshold (Sep 4 to 6 is similar):

| Case score | Alerts | Recall (all laundering) | Recall (pattern laundering) | Precision | Alerts per true case |
|---|---|---|---|---|---|
| 5 or more | 23,911 | 43.5% | 59.6% | 3.6% | 28.0 |
| 7 or more (high band) | 2,314 | 14.5% | 24.4% | 12.3% | 8.1 |
| 9 or more | 179 | 5.4% | 10.4% | 58.7% | 1.7 |
| 10 or more | 61 | 2.8% | 5.4% | 88.5% | 1.1 |

Transaction level, test period Sep 8 16:12 to Sep 10 (989,187 transactions, 1,074 laundering, base rate 0.11%): PR-AUC 0.036; best F1 11.3% at score 10 (precision 31.0%, recall 6.9%). The best threshold was chosen on this period, so this F1 is optimistic.

**Reading.**
- The score ranks laundering about ten times better than chance (PR-AUC 0.07 against a base rate of 0.6%), and adding the riskiest counterparty doubles PR-AUC over the subject alone.
- It is far from a deployable detector. At the high band, 88% of alerts are false and 86% of laundering accounts are missed. "Other" laundering (mostly isolated single transfers) is barely caught; pattern laundering is caught about twice as often.
- The dataset paper's trained models reach minority-class F1 of 28.7% (GIN) to 63.2% (graph features with XGBoost) on HI-Small (Altman et al., NeurIPS 2023, Table 2). Our untrained rules reach 11.3%. Differences that make this only a rough comparison: the paper trains on the first 60% of the data and may use features we hide (payment format), includes rows after Sep 10, and scores transactions directly, while our rules score accounts in a window.
- The practice-set numbers reported earlier (high band for 16 of 24 real and 3 of 24 benign alerts) were inflated by a 50% laundering rate and by seeds chosen from clean pattern accounts. They describe investigation inputs, not detection.

**Limits.** Weights and thresholds were chosen on a balanced design sample, not for natural prevalence. Some signals (currency conversion, new counterparties) are especially clean in this simulator.

**Results (2026-10-14, transaction monitoring model, `docs/decisions/0013-transaction-monitoring.md`)**

An open-source XGBoost model scores every transaction from the payment itself (amount for its currency, currency change, payment format, timing, earlier dealings between the two accounts) and from the sender's and receiver's account features for the review period. Split: IBM's benchmark split, 60/20/20 of all transactions by time (train Sep 1 to Sep 6 13:35, validation to Sep 8 16:11, test to Sep 18, including the rows after Sep 10). The alert threshold is chosen on validation and applied once to test. Run: `python scripts/train_detection.py` (about 7 minutes, no language model). Results: `evals/runs/detection/model-20261014T235452Z.json` (identical metrics to the first run of this model, 221718Z).

Test period: 1,015,882 transactions, 1,798 laundering (0.18%); 1,108 rows fall after Sep 10, and 655 of them are laundering.

| Scorer | PR-AUC | Precision | Recall | F1 | F1 without rows after Sep 10 |
|---|---|---|---|---|---|
| Model, with payment format | 0.709 | 84.4% | 61.5% | **71.2%** | 58.9% |
| Model, without payment format | 0.625 | 77.1% | 54.9% | 64.1% | 50.6% |
| Red-flag rules | 0.060 | 7.4% | 20.5% | 10.9% | 6.5% |

The paper's models on the same split and metric (minority-class F1, HI-Small; Altman et al., NeurIPS 2023, Table 2): GIN 28.7% to XGBoost with graph features 63.2%.

By alert volume, the model's top 1,000 accounts are 96% laundering against 28% for the rules.

**Alert policy** (`docs/decisions/0014-alert-queue-and-alert-policy.md`). The F1 threshold above is for the paper comparison only. The platform alerts at the score that caught 84% of laundering accounts in validation, the most it can catch at an industry-typical false-alarm rate (98% would triple the alerts at 97.6% false). On the test period this alerts 31,518 of 356,396 active accounts and catches 1,968 of 2,201 laundering accounts (89.4%); 93.8% of alerts are false. Priority bands order the work: high 1,224 alerts (89.5% real), medium 1,151 (21.9%), low 29,143 (2.1%). Below-the-line testing: the 68,332 accounts just under the threshold hold 225 laundering accounts (0.33%); a random sample of 250 of them is reviewed like alerts (it found 2). Results: `evals/runs/detection/model-20261014T235452Z.json`.

**Reading.**
- On IBM's split and metric the model scores above the paper's best reported model, with or without payment format. The threshold chosen on validation is almost the best possible on test (71.15% against a best of 71.22%), so the result is not tuned on the test set.
- Two simulator effects lift it, and both are visible in the table: payment format (ACH is 11.8% of transactions but 85% of laundering) adds about 7 points, and the rows after Sep 10 (59% laundering) add about 12. A real bank has neither, so the realistic figure here is closer to 50%.
- Every alert's strongest reason is "payment by ACH". The alerts are explained, but the explanation shows the model learned the simulator's habit.
- Account features describe the whole review period, so a payment is scored after the period ends (batch monitoring), not the moment it is made. IBM's exact feature timing may differ.

**Limits.** One training run and seed. The first version of this model scored accounts, not transactions, on the primary period only and without payment format: account PR-AUC 0.274 and transaction F1 24.8% (`evals/runs/detection/model-20261014T214623Z.json`, decision 0012, superseded).

## B. Investigation: given an alert, does the system get the facts right?

**Test set.** The 48 dev alerts (24 laundering seeds, 24 activity-matched benign seeds); a balanced set is acceptable here because the alert already exists. The frozen evaluation set (80 alerts) is used once, at the end.

**Metrics.** Typology accuracy, overall and on typologies reachable from the subject; evidence coverage and precision against the true pattern; recommendation outcomes (escalate, more information, close) for real and benign alerts; agreement across repeats.

**How to run.** `python evals/run_evals.py --set dev [--repeats N]` (live model, costs quota).

**Results so far** (`docs/findings/2026-10-14-evidence-coverage.md`): small model, prompt p5, one run over 48 alerts: typology 50% (code's top candidate 54%; code 13 of 15, 87%, on the five typologies it targets); evidence coverage 63%, precision 53%; real alerts escalated 63%, closed 21%; benign alerts escalated 29%. Not yet measured with the risk indicators (prompt p7).

## C. Cost

**Metrics.** Tokens, quota share and wall time per case; tool-query latency.

**Results so far.** Small model: about 15,000 tokens per case (prompt p5); 729,000 tokens for 48 cases cost 4.1% of the owner's free quota (about 0.56% per 100,000 tokens). Case file built in about 2 s. Tool queries p95 222 ms in Docker.

## D. Controls

**Metrics.** Pass or fail of the control tests; never traded for accuracy.

**Results.** Read-only tools and database (tests); malformed and oversized requests rejected or capped; the model never sees labels; every supporting transaction verified (288 of 288 injected corruptions caught, no false alarms on 24 clean cases); append-only, hash-chained audit log that rebuilds every case exactly; nothing closed without a recorded human decision; copilot answers use the same read-only tools, and citations nothing returned are flagged (tests); four-eyes rule for escalations, enforced by the API and the workflow: only a supervisor other than the escalating reviewer can confirm (tests; decision 0015).
