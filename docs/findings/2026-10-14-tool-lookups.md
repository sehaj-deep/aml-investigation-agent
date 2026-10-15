# Finding: the AI reviewer made no data lookups (prompt p8 to p9)

Date: 2026-10-14. Model: gpt-oss:20b-cloud (Ollama). Live runs, development alerts only.

## Problem

On the first live reviews of monitoring alerts (prompt p8), the AI made no tool calls and every summary said it could not check anything outside the alert window. Three lines of the prompt caused it: "stay inside the alert window", "use the tools only for what the case file lacks; many cases need no tool call at all", and "reply without a tool call". They date from the label-built practice alerts, when the code-built case file did the exploring.

## Change (p9)

- The alert window is the focus, not a limit: the tools cover the whole data (Sep 1 to Sep 18).
- Required checks before concluding, each skipped only when the case file already answers it: the subject's history over the whole data, the key counterparty (habitual hub or one-off), and the onward money (trace_funds).
- "needs_more_info" only for questions the tools cannot answer (customer background, purpose of payments).

## Measurement

Development sample: 12 queue alerts, 3 per priority band (high, medium, low, below the line), seeded, never from the frozen evaluation sample. 4 are laundering, 8 false alarms. The same alerts ran once on each prompt.

| | p8 | p9 |
|---|---|---|
| Tool calls per case | 0.08 | 2.25 |
| Laundering escalated | 0 of 4 | 2 of 4 |
| Laundering closed | 2 of 4 | 1 of 4 |
| Laundering, needs more information | 2 | 1 (the model gave no valid draft; the system fell back to human review) |
| False alarms closed | 6 of 8 | 5 of 8 |
| False alarms escalated | 0 | 1 |
| Tokens, all 12 cases | 129,798 | 267,901 |

## Reading

The required checks work: the AI follows the money and judges the counterparties, and its limitations now name real gaps. Fewer laundering cases are closed, at the cost of one more false escalation and about twice the tokens, which suits the recall-first policy. Twelve alerts show a direction, not a rate; the evaluation sample measures it. Open issues: one invalid draft, and one laundering case closed although the summary described a funnel through a hub.
