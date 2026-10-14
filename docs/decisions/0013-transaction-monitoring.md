# 0013 Transaction monitoring on IBM's split, with everything an analyst sees

Status: accepted (2026-10-14). Supersedes 0012 and the data-hiding parts of 0008.

## Why

The owner's direction: decide by how AML works in industry and by the dataset's benchmark, not by the PRD or earlier choices. Three earlier choices failed that test:

- The model scored accounts. Banks' monitoring scores payments, and an alert is the customer behind suspicious payments; the case is about the customer, and the report lists the specific transactions.
- Payment format was hidden. Analysts see it.
- Rows after Sep 10 were excluded. They are part of the data, and IBM's benchmark split includes them.

## Choice

- Score every transaction (`aml_agent/detection/transactions.py`): the payment itself (amount for its currency, currency change, same bank, self-transfer, hour, earlier payments between the two accounts in either direction, time since the sender last received, time until the receiver pays on), payment format and how usual it is for each side, and the sender's and receiver's 31 account features for the review period.
- IBM's split: 60/20/20 of all transactions by time (cutoffs 2022-09-06 13:36 and 2022-09-08 16:12, golden numbers). Account features are computed per review period, so training is cut into two periods. Validation chooses the threshold; test is scored once.
- Training keeps every laundering transaction and one in five others (seeded). Frozen evaluation-set accounts are excluded from training and validation.
- Two models: with payment format (the product model) and without (to show how much the simulator's ACH habit contributes). Both are reported, with and without the rows after Sep 10.
- An alert is an account with at least one transaction above the threshold. It carries its triggering transactions (up to 25), its score and rank, and the top three SHAP factors of its strongest transaction.
- The investigation tools now show payment format and every date by default (`TOOLS_SHOW_PAYMENT_FORMAT` and `TOOLS_SHOW_LATE_ROWS` can switch either off for a comparison run).

## Result

Test F1 71.2% with payment format, 64.1% without (validation threshold); 58.9% and 50.6% without the rows after Sep 10. Rules: 10.9%. The paper reports 28.7% to 63.2% on the same split. Details in `docs/SCORECARD.md`, part A.

## Limits

Payment format and the late rows are unusually predictive in this simulator, and every alert's top reason is ACH. Account features use the whole review period (batch scoring). One run and seed.
