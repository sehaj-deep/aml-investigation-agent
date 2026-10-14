# Finding: 0% evidence coverage on the first live runs (2026-10-14)

Model: `gpt-oss:20b-cloud` (dev tier), alert set v2, dev alerts only. Small samples; these are development observations, not results.

## Symptom

The first live runs showed 0% evidence coverage (share of the true pattern's transactions in the case evidence) on both positive alerts, even when the pattern name was right.

## Causes found

1. **Tool bug (fixed in fe8fd1e).** `get_neighbors(direction="in")` failed with a SQL error, so the agent could not see incoming money. dev-0001 is a fan-in, which is all incoming money, so coverage was 0 by construction.
2. **Run-to-run variation.** After the fix, dev-0001 went from 0% coverage in one run to 100% in the next with the same prompt. The cloud model is not repeatable even at temperature 0. Single runs are noise; comparisons need several alerts and repeats (Sprint 4).
3. **Over-citing.** On dev-0001 the agent cited all 14 incoming payments; 3 are the pattern. Coverage alone rewards citing everything, so the harness now also reports **evidence precision** (share of cited evidence that is in the pattern) and **seen coverage** (share of the pattern any tool returned).
4. **Shallow or misdirected exploration and misreading.** With prompt p1 the agent stopped after 3 tool calls on dev-0003 and never looked at the hub's outgoing payments.

## Prompt p2 (pattern guide from IBM AMLSim, investigation steps, cite only the structure)

| Alert | Truth | Predicted | Coverage | Precision | Seen | Tool calls |
|---|---|---|---|---|---|---|
| dev-0001 | fan-in | gather-scatter | 1.00 | 0.10 | 1.00 | 3 |
| dev-0002 | none (benign) | none | | | | 2 |
| dev-0003 | gather-scatter | cycle | 0.00 | 0.00 | 0.13 | 7 |
| dev-0004 | cycle | none | 0.00 | | 0.27 | 5 |
| dev-0005 | fan-in | gather-scatter | 0.92 | 0.92 | 1.00 | 7 |
| dev-0006 | gather-scatter | gather-scatter | 0.04 | 0.05 | 0.61 | 5 |

All 31 tool calls were accepted except two, and every citation was faithful.

Per-account check: the model often reaches the right accounts but misreads the flow. On dev-0001 the seed only receives money, yet the rationale says it "forwards the money to a hub". On dev-0005 it identified 12 of 13 pattern accounts. On dev-0003 and dev-0006 it followed the wrong counterparties and missed the hub.

## Conclusion

The coverage problem is no longer the tools or the harness; it is mostly the small model's reasoning (which accounts to follow, which direction money flows, which transactions to cite). p2 is kept because its pattern definitions come from the authoritative source, but six noisy cases cannot show whether it is better than p1.

## Next steps

- Run the same six alerts on a stronger model (`gemma4:cloud`) to see whether model size is the main lever before changing tools or prompts further.
- Consider a tool that returns the transfers among a set of accounts, so the model can cite a structure precisely.
- Measure run-to-run spread before comparing prompts (Sprint 4 repeats).

## Follow-up: hub hints, transfers-among tool, prompt p3, 3 repeats (same 6 alerts)

Commit 6024923. `gpt-oss:20b-cloud`, 18 runs (6 alerts x 3), 869,022 tokens in total.

**The model is not repeatable.** Temperature 0 and a fixed seed are sent to Ollama, yet dev-0001 run 3 times on p2 gave "none", "scatter-gather", "none" with different tool sequences. All comparisons below therefore use repeats.

| Prompt | Runs | Pattern accuracy | Evidence coverage | Evidence precision | Seen coverage | Tool calls accepted | Tokens per case | False escalations |
|---|---|---|---|---|---|---|---|---|
| p2 | 9 | 0.22 | 0.24 | 0.13 | 0.75 | 47 of 49 | 40,493 | 0 of 1 |
| p3 | 18 | 0.39 | 0.20 | 0.19 | 0.66 | 76 of 81 | 48,279 | 0 of 3 |

p3 spread across its three repeats: pattern accuracy 0.17, 0.33, 0.67 (mean 0.39, standard deviation 0.21); coverage mean 0.20 (sd 0.10); precision mean 0.19 (sd 0.03). Runs agreed with their alert's majority answer 56% of the time; majority-vote accuracy 2 of 6.

Per alert (p3 answers): dev-0001 fan-in: fan-in, stack, fan-in. dev-0002 benign: none three times (closed every time). dev-0003 gather-scatter: fan-out, fan-out, gather-scatter. dev-0004 cycle: none, random, gather-scatter. dev-0005 fan-in: stack, cycle, fan-in. dev-0006 gather-scatter: scatter-gather, fan-out, fan-in.

**Tool use.** get_neighbors 74 calls, get_transfers_among 4 (in 3 of 18 runs), get_transactions 2, trace_funds 1. The three runs that used get_transfers_among chose the wrong group of accounts (coverage 0, 0 and 0.08).

## Conclusion

- The pattern-accuracy gain from p2 to p3 (0.22 to 0.39) is inside the run-to-run spread (0.17 to 0.67 between repeats of p3 itself), so it is not a demonstrated improvement.
- Coverage and precision did not improve. The tools return about two thirds of each pattern (seen coverage 0.66), but the model mostly ignores the instruction to collect evidence with get_transfers_among and picks the wrong transactions.
- Benign handling is good on this sample (no false escalation), but only one benign alert was in it.
- With six alerts, a single repeat can swing accuracy by 50 points. Reliable comparisons need the full dev set and repeats.
- The small model's reasoning, not the tools, is the main limit. The next experiment is the same alerts on a stronger model.
