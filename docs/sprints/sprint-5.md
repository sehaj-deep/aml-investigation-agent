### Sprint 5: Rules-based alerting and detection model
**Build:** Config-driven rules engine (amount thresholds, structuring, velocity, cycles). Graph features and a baseline classifier (scikit-learn, optionally XGBoost). Chronological 60/20/20 train/validation/test split by timestamp, as the dataset authors recommend, on the 09/01 to 09/10 primary period (HI-Small cutoffs: 2022/09/06 13:36 and 2022/09/08 16:12; recompute in Sprint 0 after sorting by timestamp). Rows dated after 09/10 are excluded from train, validation and test and reported separately (decision in section 10); watch for patterns that start before a cutoff and finish after it. Class-imbalance handling. Report with and without the payment-format feature, and on all labeled rows versus pattern rows only. Replace pattern-file alerts with generated alerts.
**Done when:** The full pipeline runs on generated alerts, with detection metrics and end-to-end results reported.
**Verify:**
- Train, validation and test do not overlap in time, and no feature uses information from after the row's own timestamp. (Accounts naturally appear in several splits; that is how this benchmark is used.)
- Shuffle the labels and retrain; the score must fall to near chance.
- The model beats a majority-class baseline and the rules baseline.
- Report PR-AUC against the base rate, not accuracy.
- Re-score without the payment-format feature and report the drop (nearly all labeled laundering is ACH).
**Resume bullet template:**
> Built a graph-feature detection model (PR-AUC [X] vs a rules baseline of [Y]) that feeds the investigation agent; evaluated the pipeline end to end on [N] generated alerts.
