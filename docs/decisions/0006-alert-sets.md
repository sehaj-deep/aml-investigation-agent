# 0006 Alert set construction

Status: accepted (Sprint 0), PRD section 10 and FR-1

- Alert = `alert_id`, seed (integer bank ID, account), window. No pattern type, no other accounts. Labels are in `evals/alerts/ground_truth/`, which the agent never reads.
- Positives: per pattern type, a seeded draw of 3 dev and 5 eval blocks from the 245 seed-eligible multi-row blocks (an account in exactly one block and in no Other-laundering row). Seed: seeded draw from that block's eligible accounts.
- Window: the block's first to last transaction, padded 24 hours on each side (owner's choice).
- Benign controls: one per positive. Seed has no labeled row, sits in the same activity bucket as the positive's seed, and has at least one non-self transaction in the positive's window, which it copies exactly. Activity = non-self transaction count and distinct counterparties over the whole file, bucketed by floor(log2). The log2 bucketing is my choice; if no account fits the exact bucket, the nearest bucket is used.
- IDs (`dev-0001`, ...) are assigned after shuffling positives and controls together, so IDs carry no label.
- `runs_past_primary_period` in the ground truth marks alerts whose block has rows after 2022/09/10, so results can be reported with and without them.
- Seed 20261014, version v1. `evals/alerts/manifest.json` records the checksums and the seed_eligible table checksum.

Result (v1): dev 48 alerts (24 positive), eval 80 (40 positive). Alerts running past 09/10: dev 14, eval 42.
