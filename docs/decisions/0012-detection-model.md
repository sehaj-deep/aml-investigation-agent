# 0012 Open-source detection model (roadmap phase H)

Status: accepted (2026-10-14)

## Why

Scorecard part A showed the rules rank laundering only about ten times better than chance at natural prevalence (PR-AUC 0.07), with 88% false alerts in the high band. A bank's monitoring system decides which accounts reach an analyst; the AI investigation is only measured honestly on alerts like those. The owner approved a trained model on the condition that it stays simple and open source.

## Choice

- XGBoost (Apache 2.0) on our own DuckDB features, not IBM's snapml graph features (proprietary licence, Linux only).
- Unit: an account in a review period; positive if it sends or receives any labeled laundering transaction in it.
- 31 features computed in one SQL pass (`aml_agent/detection/features.py`): rule signals R1 to R6, network shape, per-currency standard scores of log amounts (never summed across currencies), timing, and the risk of counterparties. Payment format is never used; labels never enter the features.
- Chronological split of the primary period, following the dataset authors' 60/20/20 advice: train to Sep 6 13:35, validation to Sep 8 16:11 (early stopping and the transaction threshold only), test to Sep 10, scored once.
- Frozen evaluation-set accounts are removed from training and validation.
- Class weight: square root of the negative to positive ratio. Explanations: SHAP contributions from XGBoost, the top three factors per alert, in plain language.
- Dependencies live in `requirements-detection.txt`, apart from the service image: the model runs offline once and its alerts are files.

## Result

Test period PR-AUC 0.274 against 0.083 for the rules (base rate 0.47%); at 1,000 alerts, precision 40.1% against 14.9%. Transaction F1 24.8% with the validation threshold. Details in `docs/SCORECARD.md`, part A.

## How it is used

`scripts/train_detection.py` writes an alert queue: a seeded sample of 150 accounts from the top 2,000 of the test period, each with its score, rank and factors, and labels in a separate file. These alerts feed the investigation evaluation (part B) in place of the label-built practice alerts.

## Limits

Synthetic data with signals that are cleaner than real life. One run, one test period. Account scores are projected onto transactions for the paper comparison, which is only rough.
