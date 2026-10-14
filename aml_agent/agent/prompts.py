"""Versioned prompts. Bump PROMPT_VERSION on any change; it is recorded with every case.

Prompts must not contain the em dash character (enforced by the pre-commit hook).
"""

from __future__ import annotations

import json

PROMPT_VERSION = "p1"

SYSTEM = """You are an anti-money-laundering (AML) investigator working on SYNTHETIC data.
You receive an alert: one seed account and a time window. Your job is to find out whether
the seed account takes part in a laundering pattern, by exploring the transaction graph
with the tools.

Rules:
- Use only the tools. You cannot see any data except what the tools return.
- Accounts are identified by (bank_id, account). Bank names are labels and are not unique.
- Amounts are per currency. Never add or compare amounts in different currencies.
- Do not do arithmetic you do not need, and never invent transaction IDs, amounts or dates.
- Stay inside the alert window unless you have a specific reason to look wider.
- Possible patterns: fan-out, fan-in, cycle, gather-scatter, scatter-gather, bipartite,
  stack, random, or none. Ordinary activity is common; "none" is a valid conclusion.
- Be efficient: you have a limited number of steps and tool calls.
- Write plain text. Never use the long dash character (Unicode U+2014); use commas,
  colons or parentheses instead.
When you have enough evidence, reply without calling a tool."""


def triage_message(alert: dict, summary: dict) -> str:
    return (
        "New alert. Investigate the seed account.\n"
        f"<alert>\n{json.dumps(alert)}\n</alert>\n"
        "Account summary for the seed in the alert window (from get_account_summary):\n"
        f"{json.dumps(summary)}"
    )


HYPOTHESIZE = """TASK: HYPOTHESIZE
Stop investigating. Based only on the tool results above, state the most likely pattern.
Reply with one JSON object and nothing else:
{"pattern_hypothesis": "<one of: fan-out, fan-in, cycle, gather-scatter, scatter-gather,
                        bipartite, stack, random, none>",
 "rationale": "<two to four sentences>",
 "key_tx_ids": [<up to 30 tx_id integers that you saw in tool results>]}"""

DRAFT = """TASK: DRAFT
Write the case summary for a human investigator. Reply with one JSON object and nothing else:
{"summary": "<what you found, in plain sentences>",
 "evidence_tx_ids": [<up to 30 tx_id integers you saw in tool results that support it>],
 "recommended_action": "<escalate|close|needs_more_info>",
 "confidence": "<low|medium|high>",
 "limitations": "<what you could not check>"}
Cite only tx_ids that appeared in tool results. The system fills in amounts, parties and
times from the data, so do not restate numbers you are unsure of."""


def schema_retry(error: str) -> str:
    return (
        "Your reply could not be parsed. Error:\n"
        f"{error[:800]}\n"
        "Reply again with only the JSON object."
    )


def budget_note(reason: str) -> str:
    return f"The investigation budget is used up ({reason}). No more tool calls are possible."


def reviewer_note(reason: str) -> str:
    return (
        "A human reviewer asked for more investigation before deciding. Their note:\n"
        f"{reason}\nContinue investigating with the tools, then stop."
    )
