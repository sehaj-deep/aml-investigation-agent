# Model card: transaction monitoring model

## Overview

- **What it does:** scores every payment for money-laundering risk. An account with a payment above the alert threshold becomes an alert, with a priority band and the top three reasons in plain words.
- **Type:** gradient-boosted trees (XGBoost, open source), explained with SHAP contributions.
- **Code:** `aml_agent/detection/`, trained by `scripts/train_detection.py` (no language model).
- **Decisions:** `docs/decisions/0012` (first version, superseded), `0013`, `0014`.

## Intended use

Ranking payments and accounts for review by analysts in a sandbox AML case manager. It raises alerts; it never decides that an account launders. Not for real customers or real transactions.

## Data

- **Dataset:** IBM AMLworld HI-Small, synthetic (about 5 million transactions over 18 days; CDLA-Sharing 1.0).
- **Split:** IBM's benchmark split, 60/20/20 of transactions by time:
  - train to 2022-09-06 13:35;
  - validation to 2022-09-08 16:11 (early stopping and thresholds only);
  - test to the end, scored once.
- **Training sample:** all laundering transactions and one in five others.
- **Held out:** accounts of the frozen investigation evaluation set are excluded from training and validation.

## Features (about 80)

- **The payment:** amount for its currency, currency change, payment format, timing, earlier dealings between the two accounts.
- **Both accounts' behaviour in the review period:** red-flag rule signals, network shape, per-currency amount scores, timing, and the risk of their counterparties.

Amounts are never added across currencies, and labels never enter the features.

## Performance (test period, `docs/SCORECARD.md` part A)

| Measure | Result |
|---|---|
| Transaction F1, with payment format | 71.2% (PR-AUC 0.709) |
| Without payment format | 64.1% |
| Without the rows after Sep 10 | 58.9% (with format), 50.6% (without) |
| Red-flag rules, same split | 10.9% |
| IBM paper, same split and metric | 28.7% to 63.2% |

**Alert policy:** the threshold catches 84% of laundering accounts in validation. On test it alerts 31,518 accounts and catches 1,968 of 2,201 laundering accounts (89.4%), with 93.8% of alerts false. Priority bands only order the work:
- high: 89.5% real;
- medium: 21.9% real;
- low: 2.1% real.

A random below-the-line sample of 250 accounts just under the threshold measures what is missed.

## Limits and risks

- **Synthetic shortcuts:**
  - 85% of laundering uses ACH, against 11.8% of all payments, and every alert's strongest reason is "payment by ACH";
  - the rows after Sep 10 are 59% laundering.

  Both inflate results; the figures without them are reported alongside.
- **Batch scoring:** account features describe the whole review period, so a payment is scored after the period ends, not in real time.
- **Single run:** one training run and seed, with no spread across seeds.
- **Real-world validity:** real-world performance is unknown.
