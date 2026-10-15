"""Investigator copilot: answers an analyst's questions about one case.

The copilot works beside the analyst after the AI review. Each question runs a short
tool loop over the same read-only MCP tools as the investigation (the only route to
data), starting from what the case already holds: the code-built case file, the AI
assessment and the flagged payments, plus the recent conversation.

Every transaction the answer cites ("tx 123") is checked against what the case and the
tools returned; citations nothing returned are reported as unverified. Questions, tool
calls and answers go to the audit log. The copilot advises; it never decides.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from aml_agent.agent.graph import MAX_TOOL_CONTENT_CHARS, _collect_tx_ids
from aml_agent.audit import AuditSink
from aml_agent.instrument import NullAudit
from aml_agent.llm.base import ChatProvider
from aml_agent.tools.client import GraphClient

COPILOT_VERSION = "c1"
MAX_TOOL_CALLS = 6
MAX_STEPS = 6
MAX_TOKENS = 60_000
HISTORY_TURNS = 6
MAX_QUESTIONS = 25

LIMIT_NOTE = (
    "You have reached the lookup limit. Answer now with what you found, "
    "and say what is left unchecked."
)
CITATION_RE = re.compile(r"\btx\s*#?\s*(\d{1,9})\b", re.I)

SYSTEM = """You are an anti-money-laundering (AML) investigation copilot working on SYNTHETIC
data. You help a human analyst who is reviewing one case. Answer the analyst's question.

Rules:
- Use only the tools and the case context below. Never invent accounts, amounts, dates or
  transaction IDs.
- The tools are read-only and cover the whole data, from 2022-09-01T00:00 to
  2022-09-18T23:59; the alert window is the focus, not a limit.
- Accounts are identified by (bank_id, account). The case context labels them A0, A1, ...
  Call A0 "the subject" (never "the seed") and the others by their labels (A1, A2, ...).
- Amounts are per currency. Never add or compare amounts in different currencies.
- Cite transactions you rely on as "tx <id>", only IDs that the context or a tool returned.
- Answer in a few plain sentences or a short list. Say what you checked. If the tools
  cannot answer (customer background, purpose of payments), say so.
- You advise; the analyst decides. Do not tell the analyst which decision to record.
- Write plain text. Never use the long dash character (Unicode U+2014); use commas, colons
  or parentheses instead.
When you have the answer, reply without calling a tool."""

# Plain words for the tool steps the analyst sees while the copilot works.
TOOL_TEXT = {
    "get_account_summary": "Looked up account totals",
    "get_neighbors": "Listed counterparties",
    "trace_funds": "Followed the money",
    "get_transactions": "Read transactions",
    "get_account_behavior": "Checked account behavior",
    "get_transfers_among": "Read transfers between accounts",
}


def context_message(case: dict) -> str:
    """The case as the copilot sees it: the alert, the case file, the AI assessment."""
    alert = case["alert"]
    head = {
        k: alert[k] for k in ("alert_id", "seed_bank", "seed_account", "window_start", "window_end")
    }
    analysis = case.get("analysis") or {}
    draft = case.get("draft") or {}
    parts = [f"CASE CONTEXT\n<alert>\n{json.dumps(head)}\n</alert>"]
    if analysis.get("case_file"):
        parts.append(analysis["case_file"])
    if draft:
        parts.append(
            "AI ASSESSMENT (advisory): "
            f"recommendation {draft.get('recommended_action')}, confidence "
            f"{draft.get('confidence')}, suspected pattern {draft.get('pattern_hypothesis')}.\n"
            f"Summary: {draft.get('summary')}\nNot checked: {draft.get('limitations')}"
        )
        evidence = ", ".join(f"tx {e['tx_id']}" for e in draft.get("evidence", [])[:40])
        if evidence:
            parts.append(f"Supporting transactions chosen by the review: {evidence}.")
    return "\n\n".join(parts)


def known_tx_ids(case: dict) -> set[int]:
    """Transaction IDs the case already holds (case file, flagged payments, evidence)."""
    out: list[int] = []
    _collect_tx_ids(case.get("case_graph") or {}, out)
    _collect_tx_ids((case.get("analysis") or {}).get("triggers") or [], out)
    _collect_tx_ids((case.get("draft") or {}).get("evidence") or [], out)
    return set(out)


def cited_tx_ids(text: str) -> list[int]:
    return list(dict.fromkeys(int(m.group(1)) for m in CITATION_RE.finditer(text)))


def tool_text(name: str, arguments: dict, labels: dict[tuple[int, str], str]) -> str:
    what = TOOL_TEXT.get(name, name)
    acc = (arguments.get("bank_id"), arguments.get("account"))
    if acc in labels:
        label = labels[acc]
        what += f" for {'the subject' if label == 'A0' else label}"
    return what


@dataclass
class Answer:
    question: str
    answer: str
    tools: list[dict] = field(default_factory=list)
    cited: list[int] = field(default_factory=list)
    unverified: list[int] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    model: str = ""
    version: str = COPILOT_VERSION
    stopped: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


async def ask(
    provider: ChatProvider,
    client: GraphClient,
    case: dict,
    question: str,
    history: list[dict] | None = None,
    audit: AuditSink | None = None,
) -> AsyncIterator[dict]:
    """Answer one question. Yields {"type": "tool", ...} events, then {"type": "answer"}."""
    audit = audit or NullAudit()
    case_id = case["case_id"]
    started = time.perf_counter()
    labels = {
        (int(acc[0]), str(acc[1])): label
        for label, acc in ((case.get("analysis") or {}).get("aliases") or {}).items()
    }
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": context_message(case)},
        {"role": "assistant", "content": "I have the case context. What would you like to know?"},
    ]
    for turn in (history or [])[-HISTORY_TURNS:]:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": question})
    await audit.emit(case_id, "copilot_question", {"question": question}, actor="analyst")

    seen = known_tx_ids(case)
    result = Answer(question=question, answer="", model=provider.model)
    specs = await client.tool_specs()
    known = {s["function"]["name"] for s in specs}
    for _ in range(MAX_STEPS):
        tokens = result.input_tokens + result.output_tokens
        over = len(result.tools) >= MAX_TOOL_CALLS or tokens >= MAX_TOKENS
        resp = await provider.chat(messages, tools=None if over else specs)
        result.input_tokens += resp.input_tokens
        result.output_tokens += resp.output_tokens
        await audit.emit(
            case_id,
            "model_call",
            {
                "model": provider.model,
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
                "purpose": "copilot",
            },
            actor="copilot",
        )
        messages.append(resp.as_message())
        if not resp.tool_calls:
            result.answer = resp.content.strip()
            break
        for call in resp.tool_calls:
            if len(result.tools) >= MAX_TOOL_CALLS or call.name not in known:
                content = json.dumps({"error": "tool limit reached or unknown tool"})
            else:
                res = await client.call(call.name, call.arguments)
                if res.ok:
                    found: list[int] = []
                    _collect_tx_ids(res.content, found)
                    seen.update(found)
                    content = json.dumps(res.content)[:MAX_TOOL_CONTENT_CHARS]
                else:
                    content = json.dumps({"error": res.error})
                step = {
                    "name": call.name,
                    "text": tool_text(call.name, call.arguments, labels),
                    "ok": res.ok,
                }
                result.tools.append(step)
                await audit.emit(
                    case_id,
                    "tool_call",
                    {
                        "name": call.name,
                        "arguments": call.arguments,
                        "ok": res.ok,
                        "duration_ms": round(res.duration_ms, 1),
                        "purpose": "copilot",
                    },
                    actor="copilot",
                )
                yield {"type": "tool", **step}
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": content}
            )
    else:
        # Out of steps: one last turn without tools, so the analyst gets what was found.
        result.stopped = "lookup limit"
        messages.append({"role": "user", "content": LIMIT_NOTE})
        resp = await provider.chat(messages, tools=None)
        result.input_tokens += resp.input_tokens
        result.output_tokens += resp.output_tokens
        result.answer = resp.content.strip()
    if not result.answer:
        result.answer = "I could not finish this question within my limits. Please narrow it."
        result.stopped = result.stopped or "no answer"
    result.answer = result.answer.replace(chr(0x2014), ", ")
    result.cited = cited_tx_ids(result.answer)
    result.unverified = [t for t in result.cited if t not in seen]
    result.seconds = round(time.perf_counter() - started, 1)
    await audit.emit(
        case_id,
        "copilot_answer",
        {
            "answer": result.answer,
            "cited": result.cited,
            "unverified": result.unverified,
            "tools": [t["name"] for t in result.tools],
            "version": COPILOT_VERSION,
        },
        actor="copilot",
    )
    yield {"type": "answer", **result.as_dict()}
