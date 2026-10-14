"""The investigation workflow (FR-3).

    triage -> agent <-> tools -> hypothesize -> draft -> human_review -> finalize
                ^                                            |
                +------------- request_more -----------------+

- triage (code): fetches the seed's account summary through MCP.
- agent / tools: the LLM tool loop. Hard limits on steps, tool calls and tokens.
- hypothesize, draft (LLM): JSON replies validated with Pydantic, one retry each.
  The model names tx_ids; code fetches the evidence rows through MCP, so the model
  never writes amounts, parties or times (FR-3: no lookups the code can do).
- human_review: LangGraph interrupt. Resumes only with a validated Decision.
- finalize: refuses to run without an approve or reject decision.
State is checkpointed after every node (thread_id = case_id), so a paused case
survives a restart.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, ValidationError

from aml_agent.agent import prompts
from aml_agent.llm.base import ChatProvider
from aml_agent.schemas.case import Case, Decision, DraftReply, Evidence, HypothesisReply
from aml_agent.tools.client import GraphClient

EM_DASH = chr(0x2014)
MAX_TOOL_CONTENT_CHARS = 12_000


@dataclass(frozen=True)
class Budget:
    max_steps: int = 12  # LLM turns in the investigate loop, per review round
    max_tool_calls: int = 20  # per review round
    max_tokens: int = 120_000  # input plus output, whole case
    max_review_rounds: int = 2  # "request more" rounds


class FinalizeRefused(RuntimeError):
    """Raised when finalize is reached without a recorded approve or reject decision."""


class CaseState(TypedDict, total=False):
    case_id: str
    alert: dict
    provider: str
    model: str
    prompt_version: str
    messages: list[dict]
    tool_log: list[dict]
    seen_tx_ids: list[int]
    steps: int
    tool_calls: int
    round_steps: int
    round_tool_calls: int
    invalid_tool_calls: int
    input_tokens: int
    output_tokens: int
    llm_latency_ms: float
    budget_exhausted: str | None
    schema_attempts: int
    schema_failures: int
    hypothesis: dict | None
    cited_tx_ids: list[int]
    case: dict | None
    warnings: list[str]
    decisions: list[dict]
    review_round: int
    next_after_review: str
    status: str


def _collect_tx_ids(obj: Any, out: list[int]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "tx_id" and isinstance(v, int):
                out.append(v)
            elif k == "tx_ids" and isinstance(v, list):
                out.extend(x for x in v if isinstance(x, int))
            else:
                _collect_tx_ids(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_tx_ids(v, out)


def _extract_json(text: str) -> str:
    """The first {...} block in a reply (models sometimes wrap JSON in prose or fences)."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON object found")
    return match.group(0)


def _strip_em_dash(text: str, warnings: list[str], field: str) -> str:
    if EM_DASH in text:
        warnings.append(f"em dash removed from {field}")
        return text.replace(f" {EM_DASH} ", ", ").replace(EM_DASH, ", ")
    return text


def build_graph(provider: ChatProvider, client: GraphClient, budget: Budget | None = None):
    budget = budget or Budget()

    async def triage(state: CaseState) -> CaseState:
        alert = state["alert"]
        args = {
            "bank_id": alert["seed_bank"],
            "account": alert["seed_account"],
            "window_start": alert["window_start"],
            "window_end": alert["window_end"],
        }
        result = await client.call("get_account_summary", args)
        summary = result.content if result.ok else {"error": result.error}
        seen: list[int] = []
        return {
            "provider": provider.provider,
            "model": provider.model,
            "prompt_version": prompts.PROMPT_VERSION,
            "messages": [
                {"role": "system", "content": prompts.SYSTEM},
                {"role": "user", "content": prompts.triage_message(alert, summary)},
            ],
            "tool_log": [
                {
                    "by": "system",
                    "step": 0,
                    "name": "get_account_summary",
                    "arguments": args,
                    "ok": result.ok,
                    "error": result.error,
                    "duration_ms": round(result.duration_ms, 1),
                }
            ],
            "seen_tx_ids": seen,
            "steps": 0,
            "tool_calls": 0,
            "round_steps": 0,
            "round_tool_calls": 0,
            "invalid_tool_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "llm_latency_ms": 0.0,
            "budget_exhausted": None,
            "schema_attempts": 0,
            "schema_failures": 0,
            "warnings": [],
            "decisions": [],
            "review_round": 0,
            "status": "investigating",
        }

    def _usage(state: CaseState, resp) -> dict:
        return {
            "input_tokens": state["input_tokens"] + resp.input_tokens,
            "output_tokens": state["output_tokens"] + resp.output_tokens,
            "llm_latency_ms": state["llm_latency_ms"] + resp.latency_ms,
        }

    async def agent(state: CaseState) -> CaseState:
        specs = await client.tool_specs()
        resp = await provider.chat(state["messages"], tools=specs)
        return {
            "messages": [*state["messages"], resp.as_message()],
            "steps": state["steps"] + 1,
            "round_steps": state["round_steps"] + 1,
            "invalid_tool_calls": state["invalid_tool_calls"] + resp.invalid_tool_calls,
            **_usage(state, resp),
        }

    def _exhausted(state: CaseState) -> str | None:
        if state["round_steps"] >= budget.max_steps:
            return f"step limit {budget.max_steps}"
        if state["round_tool_calls"] >= budget.max_tool_calls:
            return f"tool call limit {budget.max_tool_calls}"
        if state["input_tokens"] + state["output_tokens"] >= budget.max_tokens:
            return f"token limit {budget.max_tokens}"
        return None

    def after_agent(state: CaseState) -> str:
        last = state["messages"][-1]
        return "tools" if last.get("tool_calls") else "hypothesize"

    async def tools(state: CaseState) -> CaseState:
        specs = await client.tool_specs()
        known = {s["function"]["name"] for s in specs}
        messages = list(state["messages"])
        log = list(state["tool_log"])
        seen = list(state["seen_tx_ids"])
        n_calls, round_calls = state["tool_calls"], state["round_tool_calls"]
        invalid = state["invalid_tool_calls"]
        for call in messages[-1]["tool_calls"]:
            entry = {
                "by": "agent",
                "step": state["steps"],
                "name": call["name"],
                "arguments": call["arguments"],
            }
            if round_calls >= budget.max_tool_calls:
                content = json.dumps({"error": prompts.budget_note("tool call limit")})
                entry.update(ok=False, error="budget", duration_ms=0.0, executed=False)
            elif call["name"] not in known:
                invalid += 1
                n_calls += 1
                round_calls += 1
                content = json.dumps({"error": f"unknown tool {call['name']!r}"})
                entry.update(ok=False, error="unknown tool", duration_ms=0.0, executed=False)
            else:
                n_calls += 1
                round_calls += 1
                result = await client.call(call["name"], call["arguments"])
                if result.ok:
                    _collect_tx_ids(result.content, seen)
                    content = json.dumps(result.content)
                    if len(content) > MAX_TOOL_CONTENT_CHARS:
                        content = (
                            content[:MAX_TOOL_CONTENT_CHARS]
                            + ' ... [truncated: narrow the window or lower the limit]"'
                        )
                else:
                    invalid += 1
                    content = json.dumps({"error": result.error})
                entry.update(
                    ok=result.ok,
                    error=result.error,
                    duration_ms=round(result.duration_ms, 1),
                    executed=True,
                )
            log.append(entry)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": call["name"],
                    "content": content,
                }
            )
        update: CaseState = {
            "messages": messages,
            "tool_log": log,
            "seen_tx_ids": list(dict.fromkeys(seen)),
            "tool_calls": n_calls,
            "round_tool_calls": round_calls,
            "invalid_tool_calls": invalid,
        }
        return update

    def after_tools(state: CaseState) -> str:
        return "hypothesize" if _exhausted(state) else "agent"

    async def _structured(
        state: CaseState, instruction: str, model: type[BaseModel]
    ) -> tuple[BaseModel | None, dict]:
        messages = [*state["messages"], {"role": "user", "content": instruction}]
        attempts, failures = state["schema_attempts"], state["schema_failures"]
        usage = {k: state[k] for k in ("input_tokens", "output_tokens", "llm_latency_ms")}
        parsed = None
        for _ in range(2):
            resp = await provider.chat(messages)
            usage = {
                "input_tokens": usage["input_tokens"] + resp.input_tokens,
                "output_tokens": usage["output_tokens"] + resp.output_tokens,
                "llm_latency_ms": usage["llm_latency_ms"] + resp.latency_ms,
            }
            messages.append(resp.as_message())
            attempts += 1
            try:
                parsed = model.model_validate_json(_extract_json(resp.content))
                break
            except (ValueError, ValidationError) as exc:
                failures += 1
                messages.append({"role": "user", "content": prompts.schema_retry(str(exc))})
        return parsed, {
            "messages": messages,
            "schema_attempts": attempts,
            "schema_failures": failures,
            **usage,
        }

    async def hypothesize(state: CaseState) -> CaseState:
        reason = _exhausted(state)
        instruction = prompts.HYPOTHESIZE
        if reason:
            instruction = prompts.budget_note(reason) + "\n\n" + instruction
        parsed, update = await _structured(state, instruction, HypothesisReply)
        warnings = list(state["warnings"])
        if parsed is None:
            warnings.append("MODEL_OUTPUT_INVALID: hypothesis reply failed validation twice")
            hypothesis = None
        else:
            hypothesis = parsed.model_dump()
            hypothesis["rationale"] = _strip_em_dash(hypothesis["rationale"], warnings, "rationale")
        return {
            **update,
            "hypothesis": hypothesis,
            "budget_exhausted": reason,
            "warnings": warnings,
        }

    async def draft(state: CaseState) -> CaseState:
        parsed, update = await _structured(state, prompts.DRAFT, DraftReply)
        warnings = list(state["warnings"])
        hypothesis = state.get("hypothesis")
        if parsed is None:
            warnings.append("MODEL_OUTPUT_INVALID: draft reply failed validation twice")
            reply = DraftReply(
                summary="The model did not produce a valid case draft.",
                evidence_tx_ids=[],
                recommended_action="needs_more_info",
                confidence="low",
                limitations="No valid model output; a human must investigate.",
            )
        else:
            reply = parsed
        cited = list(dict.fromkeys(reply.evidence_tx_ids))
        seen = set(state["seen_tx_ids"])
        unseen = [t for t in cited if t not in seen]
        if unseen:
            warnings.append(f"cited tx_ids never returned by a tool: {unseen}")
        evidence: list[Evidence] = []
        log = list(state["tool_log"])
        if cited:
            result = await client.call("get_transactions", {"tx_ids": cited})
            log.append(
                {
                    "by": "system",
                    "step": state["steps"],
                    "name": "get_transactions",
                    "arguments": {"tx_ids": cited},
                    "ok": result.ok,
                    "error": result.error,
                    "duration_ms": round(result.duration_ms, 1),
                    "executed": True,
                }
            )
            if result.ok:
                if result.content["not_found"]:
                    warnings.append(f"cited tx_ids not in the data: {result.content['not_found']}")
                for r in result.content["transactions"]:
                    evidence.append(
                        Evidence(
                            tx_id=r["tx_id"],
                            from_bank=str(r["from_bank"]),
                            from_account=r["from_account"],
                            to_bank=str(r["to_bank"]),
                            to_account=r["to_account"],
                            amount_paid=r["amount_paid"],
                            currency_paid=r["currency_paid"],
                            timestamp=r["timestamp"],
                        )
                    )
            else:
                warnings.append(f"evidence lookup failed: {result.error}")
        case = Case(
            case_id=state["case_id"],
            pattern_hypothesis=hypothesis["pattern_hypothesis"] if hypothesis else "none",
            summary=_strip_em_dash(reply.summary, warnings, "summary"),
            evidence=evidence,
            recommended_action=reply.recommended_action,
            confidence=reply.confidence,
            limitations=_strip_em_dash(reply.limitations, warnings, "limitations"),
        )
        if hypothesis is None:
            warnings.append("pattern_hypothesis defaulted to none because the hypothesis failed")
        return {
            **update,
            "tool_log": log,
            "cited_tx_ids": cited,
            "case": case.model_dump(),
            "warnings": warnings,
            "status": "pending_review",
        }

    async def human_review(state: CaseState) -> CaseState:
        raw = interrupt(
            {"case_id": state["case_id"], "case": state["case"], "warnings": state["warnings"]}
        )
        decision = Decision.model_validate(raw)
        decisions = [*state["decisions"], decision.model_dump(mode="json")]
        if decision.action != "request_more":
            return {"decisions": decisions, "next_after_review": "finalize"}
        if state["review_round"] >= budget.max_review_rounds:
            warnings = [
                *state["warnings"],
                "more investigation was requested but the review-round limit is reached; "
                "approve or reject",
            ]
            return {
                "decisions": decisions,
                "warnings": warnings,
                "next_after_review": "human_review",
            }
        return {
            "decisions": decisions,
            "review_round": state["review_round"] + 1,
            "round_steps": 0,
            "round_tool_calls": 0,
            "messages": [
                *state["messages"],
                {"role": "user", "content": prompts.reviewer_note(decision.reason)},
            ],
            "status": "investigating",
            "next_after_review": "agent",
        }

    async def finalize(state: CaseState) -> CaseState:
        decisions = state.get("decisions") or []
        last = decisions[-1] if decisions else None
        if not last or last["action"] not in ("approve", "reject"):
            raise FinalizeRefused(
                f"case {state.get('case_id')}: finalize needs a recorded approve or reject"
            )
        return {"status": "approved" if last["action"] == "approve" else "rejected"}

    g = StateGraph(CaseState)
    g.add_node("triage", triage)
    g.add_node("agent", agent)
    g.add_node("tools", tools)
    g.add_node("hypothesize", hypothesize)
    g.add_node("draft", draft)
    g.add_node("human_review", human_review)
    g.add_node("finalize", finalize)
    g.add_edge(START, "triage")
    g.add_edge("triage", "agent")
    g.add_conditional_edges("agent", after_agent, ["tools", "hypothesize"])
    g.add_conditional_edges("tools", after_tools, ["agent", "hypothesize"])
    g.add_edge("hypothesize", "draft")
    g.add_edge("draft", "human_review")
    g.add_conditional_edges(
        "human_review",
        lambda s: s["next_after_review"],
        ["finalize", "agent", "human_review"],
    )
    g.add_edge("finalize", END)
    return g, finalize


def compile_graph(provider, client, checkpointer, budget: Budget | None = None):
    g, _ = build_graph(provider, client, budget)
    return g.compile(checkpointer=checkpointer)
