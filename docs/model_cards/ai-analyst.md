# Model card: AI analyst (review agent, copilot and SAR drafting)

## Overview

- **What it does:**
  - investigates a monitoring alert and drafts an assessment: suspected pattern, supporting transactions, guidance citations, and a recommendation (escalate, close or needs more information);
  - answers an analyst's questions about a case (copilot);
  - drafts the narrative of a suspicious activity report after a confirmed escalation.
- **Model:** gpt-oss:20b through Ollama's cloud service, temperature 0. Prompts are versioned in code:
  - review: p10 in the final evaluation, p11 now;
  - copilot: c2;
  - SAR draft: s4.
- **Code:** `aml_agent/agent/` (LangGraph workflow, case file, copilot, SAR draft).

## Intended use

Decision support for an AML analyst in a sandbox. The AI advises; people decide:
- every case needs a recorded analyst decision with a reason;
- escalations and SAR approvals need a second person with the supervisor role (four-eyes), enforced by the API and the workflow.

## How it is grounded

- **One route to data:** the model reads data only through read-only, bounded MCP tools and never sees labels.
- **Code supplies the facts:** code builds the case file, the evidence rows, the SAR facts and every amount.
- **Code checks the output:**
  - cited transactions are verified against the source data;
  - transactions mentioned in the summary must have been returned by a tool;
  - guidance quotes must match their passage word for word;
  - SAR amounts and citations are checked, and the SAR may not claim to have been filed.

## Evaluation (`docs/findings/2026-10-15-final-evaluation.md`)

150 monitoring alerts, frozen before the run (tag `eval-freeze`), 50 per priority band: 55 laundering and 95 false alarms. One pass with prompt p10.

| Recommendation | Laundering | False alarms |
|---|---|---|
| Escalate | 49.1% | 25.3% |
| Needs more information | 18.2% | 38.9% |
| Close | 32.7% | 35.8% |

- **Faithfulness:**
  - supporting evidence verified in 150 of 150 cases;
  - 149 of 150 drafts valid;
  - 186 of 280 guidance quotes verbatim and kept, 94 dropped.
- **Cost:** median 22,150 tokens and 49 seconds per case.
- **Copilot:** answers in about 5 to 20 seconds.
- **Retrieval:** hybrid guidance search puts the right document first 88.9% of the time on 18 questions.

## Prompt injection (`docs/findings/2026-10-15-prompt-injection.md`)

- **Scripted model that obeys an injection:** every action is refused or flagged by code.
- **Live spot check, 4 hostile copilot questions:**
  - takeover, prompt leak and fake evidence: refused;
  - decision steering: partly followed (the model advised escalating), but no case changed.

## Limits and risks

- **Its "close" is not reliable:** it closed a third of laundering in the evaluation, so it must not close cases on its own.
- **Coverage of the evaluation:**
  - one model and one pass on synthetic data;
  - the medium and low bands contained few laundering cases (7 and 2);
  - no analyst-time study.
- **The model can be steered** into giving decision advice; controls stop it from acting, not from saying things.
- **No customer data:** the data has none, so narratives identify accounts by number only.
- **No authentication:** roles are self-declared in the demo, so the four-eyes rule is a checked and audited workflow control.
