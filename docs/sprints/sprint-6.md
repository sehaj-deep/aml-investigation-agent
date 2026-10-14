### Sprint 6: Hardening
**Build:** Prompt-injection test suite (AgentDojo-style cases) against tool outputs, using an added and disclosed synthetic text field. Optional smolagents analysis step in a locked-down Docker sandbox. Generated model card per agent (purpose, risk rating, data lineage, test results).
**Done when:** Injection tests run in CI and results are reported before and after defenses.
**Verify:**
- Run the injection suite before and after defenses.
- Attempt an injected tool call outside the allowlist; it must be blocked.
- If the sandbox exists, try network access from inside it; it must fail.
- Diff the generated model card against the real configuration.
**Resume bullet template:**
> Red-teamed the agent with [N] prompt-injection cases, reducing attack success from [X]% to [Y]%, and generated per-agent model cards documenting controls and test results.
