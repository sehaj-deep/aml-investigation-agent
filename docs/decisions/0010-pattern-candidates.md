# 0010 Pattern candidates found by code (roadmap phase C)

Status: accepted (2026-10-14)

## Why

With the case file in place (prompt p4), the small model's remaining failure was choosing the pattern's accounts: it took the seed's ordinary counterparties for the pattern, or named only part of a hub's group. Finding a structure in a small graph is deterministic work, so code proposes the structures and the model judges them.

## Signal (measured on dev alerts, ground truth used for analysis only)

In the seeds' two-step neighborhoods (3,937 transfers, 209 of them pattern transfers), every pattern transfer sits on a one-off relationship: the pair transacts once (191) or twice (18) in the window. Ordinary activity mostly repeats (pairs with 6 to 12 transfers). Keeping pairs with at most 2 transfers keeps 100% of pattern transfers and removes 85% of the rest. Real-world analog: payments to new or unusual counterparties that break an account's normal behavior. The effect is especially clean in this simulator and must be reported that way.

## Design (`aml_agent/analysis/patterns.py`)

From the case file's graph, over one-off relationships reachable from the seed, code builds candidates and ranks them:
- cycle: a loop through the seed from the 8-step traces;
- scatter-gather: an origin and a sink linked through two or more intermediaries;
- fan-in, fan-out, gather-scatter: a hub with three or more one-off links (by direction);
- random: a time-ordered chain of three or more one-off transfers through the seed.

The case file marks one-off relationships and lists the top three candidates (C1 to C3) as leads, not verdicts. The model may adopt a candidate by id ("C1"); code expands it to its accounts and collects the evidence as before.

Bipartite and stack patterns are often several disconnected pieces (7% to 33% of their transfers are reachable from the seed), so no candidate kind targets them.

## Results on dev (24 positives, 24 benign)

| | Code, top candidate | Code, top three |
|---|---|---|
| Right kind, all positives | 13 of 24 (54%) | 17 of 24 (71%) |
| Right kind, excluding bipartite and stack | 13 of 18 (72%) | 17 of 18 (94%) |
| Evidence coverage / precision of the top candidate | 0.53 / 0.53 | |

Benign: code finds no candidate for 9 of 24 benign seeds; the other 15 get candidates, so shape alone cannot decide suspicion. That judgment belongs to the detection score (phase B), the LLM and the reviewer.

On the five positive alerts of the earlier live runs, the top candidate was right 4 of 5 times (80%) every time, against 53% for the small model's own call (prompt p4, 15 runs).

## Limits

- Parameters (one-off = at most 2 transfers, hub = 3 or more links, chains of 3 to 8) were chosen on dev alerts; the frozen evaluation set gives the honest number.
- Candidates are restricted to the case file's two-step neighborhood plus loops.
