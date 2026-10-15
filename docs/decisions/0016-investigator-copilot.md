# 0016 Investigator copilot

Status: accepted (2026-10-14)

## Why

After the AI review, an analyst has follow-up questions: has the subject dealt with these counterparties before, where did the money go next, is the main counterparty a regular hub or a new account? Answering them by hand means more lookups. The copilot answers them in the case, with the same data access and controls as the AI review.

## Choice (`aml_agent/agent/copilot.py`)

- A chat panel on the case screen. Each question runs a short tool loop: at most 6 lookups and 60,000 tokens, then a final turn without tools, so the analyst always gets what was found.
- Same route to data as the review: the read-only MCP tools, no labels. Each question starts from the code-built case file (now stored with the case), the AI assessment, the flagged payments and the last six turns of the conversation.
- It runs in the API, not the case queue, so an answer comes back in seconds. The analyst sees each lookup as it happens (server-sent events, unbuffered through nginx).
- Every transaction the answer cites ("tx 123") is checked against what the case and the lookups returned. Unchecked citations are shown in red as "not found". Cited transactions can be shown in the network map.
- Questions, lookups, model calls and answers go to the audit log (actors "analyst" and "copilot"), and the chat is stored with the case (`copilot_messages`).
- At most 25 questions per case, to protect the model quota. The copilot advises and cannot change a case or record a decision.

## Measured (live, gpt-oss:20b-cloud)

Three questions on one case answered in 5 to 12 seconds with 1 to 2 lookups each, using about 5,000 to 8,000 tokens. Answers said what was checked; none cited a transaction ID, so citation checking is exercised by the tests, not by these answers.

## Limits

Answers are not yet evaluated at scale. The copilot does not see the bank's customer data (none exists in this dataset), so questions about purpose or background are answered as unknown.
