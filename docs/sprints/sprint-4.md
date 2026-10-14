### Sprint 4: Evaluation, ablation and final run
**Build:** pytest eval harness. GitHub Actions gates that run on deterministic checks and recorded fixtures only. The deterministic no-LLM pipeline and the ablation (section 12). A judge model validated against a small human-labeled set. Written failure analysis. **Freeze, tag, then run the frozen evaluation set on the report-tier model** (uncached, one model per table), and report dev-tier and report-tier results side by side.
**Done when:** A pull request fails CI if faithfulness, retrieval or latency regresses, and the final results table exists.
**Verify:**
- Break it on purpose (bad prompt, retrieval k=1, tiny tool budget) and confirm CI fails; confirm the real version passes.
- Label 30-50 narratives yourself and report judge agreement.
- Repeat a run 3-5 times, if quota allows, to see run-to-run spread, and set thresholds outside the noise.
- Confirm the evaluation set was not used for any prompt change since the freeze tag.
- Confirm the deterministic pipeline got a fair, time-boxed effort and was frozen before its evaluation results were looked at.
**Resume bullet templates:**
> Built a CI evaluation harness gating on citation faithfulness, retrieval quality and latency, with an LLM judge calibrated to [X]% agreement with human labels.
> Ablation: compared the agent against a deterministic pipeline on [N] frozen alerts; the agent improved pattern accuracy from [X]% to [Y]% at [Z]x the cost.
