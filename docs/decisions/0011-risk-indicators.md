# 0011 Rules-based behavioral risk indicators (roadmap phase B)

Status: accepted (2026-10-14)

## Why

On all 48 dev alerts the small model escalated 63% of real cases and 29% of benign ones (prompt p5). The case file only showed who paid whom, and the benign controls were chosen to look alike in activity, so shape alone could not separate them. Investigators judge suspicion on behavior; code can measure behavior exactly.

## Signals and rules (`aml_agent/analysis/risk.py`, tool `get_account_behavior`)

Each rule is a recognized red flag, checked on an account's non-self transfers in the review period (primary period only, payment format never used):

| Code | Weight | Rule |
|---|---|---|
| R1 | 3 | Currency conversion pass-through: receives in one currency, pays out only in others |
| R2 | 1 | Flow-through activity: both receives and pays in the period |
| R3 | 1 | Predominantly new counterparties: at least 90% never seen before the period |
| R4 | 1 | Predominantly one-time relationships: at least 70% transact once or twice |
| R5 | 1 | Activity concentrated in the period: at least 70% of the account's transactions |
| R6 | 1 | Rapid onward transfers: at least half of incoming transfers followed by a payment within 24 hours |

Case risk = the subject's score + the highest score among up to 8 first-time counterparties (step 1, at most 2 transfers). Bands: high at 7 or more, medium 5 to 6, low below 5.

## Measurement

Design sample, excluding every evaluation-set account and block: 150 laundering accounts (seed-eligible accounts of dev and unused blocks finishing by Sep 10, with alert-style windows) and 134 activity-matched accounts with no labeled row.

- Single signals: currency switch 21% of laundering vs 0% of ordinary; receives and pays 74% vs 42%; new-counterparty share median 0.99 vs 0.46.
- Subject score alone: AUC 0.775 (0.763 on a 100/95 subset).
- Subject plus the riskiest first-time counterparty: AUC 0.906 (subset). Score 7 or more flags 54% of laundering and 5% of ordinary accounts; 5 or more, 90% and 21%.

On the 48 dev alerts (case file, code only): AUC 0.839; high band 16 of 24 real and 3 of 24 benign; low band 5 real and 16 benign.

## How it is used

The case file lists the score, band and fired rules for the subject and its riskiest first-time counterparty. The model weighs them with the network (prompt p7). The UI shows a risk badge, sorts the queue by risk, and explains each rule in plain language.

## Limits

Weights and thresholds were chosen on the design sample; the frozen evaluation set gives the honest number. Some signals (currency conversion, new counterparties) are especially clean in this simulator and must be reported that way. The score is evidence for judgment, not a verdict.
