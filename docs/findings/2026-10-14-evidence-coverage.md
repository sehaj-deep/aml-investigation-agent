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
