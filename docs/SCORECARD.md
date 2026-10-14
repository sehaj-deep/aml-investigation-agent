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

**Results (2026-10-14, detection model, `docs/decisions/0012-detection-model.md`)**

An open-source XGBoost model on 31 account features (the rule signals plus network shape, per-currency amount scores, timing and counterparty features). Chronological split of the primary period: trained on Sep 2 to Sep 6 13:35, validation (early stopping and threshold only) to Sep 8 16:11, test once on Sep 8 16:12 to Sep 10. Frozen evaluation-set accounts are removed from training and validation. Run: `python scripts/train_detection.py` (about 2 minutes, no language model). Results: `evals/runs/detection/model-20261014T214623Z.json`.

Test period: 356,183 accounts, 1,671 positive (base rate 0.47%). PR-AUC: model 0.274, rules 0.083 (validation 0.314).

| Alerts (top N) | Model precision | Model recall | Rules precision | Rules recall |
|---|---|---|---|---|
| 100 | 99.0% | 5.9% | 66.0% | 4.0% |
| 250 | 86.8% | 13.0% | 39.2% | 5.9% |
| 500 | 62.6% | 18.7% | 21.6% | 6.5% |
| 1,000 | 40.1% | 24.0% | 14.9% | 8.9% |
| 2,000 | 25.6% | 30.6% | 10.9% | 13.1% |

Transaction level (a transaction is flagged when both of its accounts score above a threshold chosen on validation; 993,724 transactions, 1,141 laundering): F1 24.8% (precision 35.8%, recall 18.9%). Best F1 on the test period itself: 25.4% (optimistic). Rules: 11.3% (optimistic).

**Reading.**
- At the same alert volume the model finds two to four times as much laundering as the rules. At 1,000 alerts, 4 in 10 are true against 1.5 in 10 for the rules.
- Transaction F1 of 24.8% is close to the paper's lowest trained baseline (GIN, 28.7%) and well below its best (63.2%). Our model scores accounts, not transactions, never sees payment format, and stops at Sep 10, so the comparison is rough.
- Most laundering is still missed: at 2,000 alerts recall is 31% (48% for pattern laundering).
- The investigation alert queue (`evals/alerts/detection/`) is a seeded sample of 150 accounts from the top 2,000, so about a quarter are real (33 of 150), like a real queue, not only the easiest cases.

**Limits.** One training run and one test period; no spread across seeds yet. Simulator signals such as currency conversion dominate the model (top features by gain: currency switch, new-counterparty share, currencies paid, rule score).

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

**Results.** Read-only tools and database (tests); malformed and oversized requests rejected or capped; the model never sees labels; every supporting transaction verified (288 of 288 injected corruptions caught, no false alarms on 24 clean cases); append-only, hash-chained audit log that rebuilds every case exactly; nothing closed without a recorded human decision; four-eyes rule for escalations (in the UI; server-side enforcement planned).
