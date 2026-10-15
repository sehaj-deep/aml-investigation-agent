"""The investigation workflow (FR-3).

    triage -> agent <-> tools -> hypothesize -> collect_evidence -> draft -> verify
                ^                                                            |
                +-- request_more <-- human_review <--------------------------+
                                       |      ^
                              close    |      | return_to_analyst
                                 v     v      |
                          finalize <-- supervisor_review  (escalate: four-eyes)

- triage (code): builds the case file through MCP (aml_agent/agent/casefile.py):
  the seed's summary, its two-step neighborhood and loops through the seed.
- agent / tools: the LLM tool loop for anything the case file lacks. Hard limits
  on steps, tool calls and tokens.
- hypothesize (LLM): the pattern and the accounts that form it (by case-file label).
- collect_evidence (code): the transfers among those accounts (get_transfers_among)
  become the evidence, so the model never picks transactions, amounts, parties or
  times (FR-3: no lookups the code can do).
- draft (LLM): the narrative, action and confidence, written with the evidence in view.
  JSON replies are validated with Pydantic, one retry each.
- verify (code): checks every cited tx_id and evidence row against the data
  (FR-7); failures become visible warnings before review.
- human_review: LangGraph interrupt. Resumes only with a validated analyst Decision:
  close, escalate or request_more.
- supervisor_review: a second interrupt for escalations. Only a supervisor who is not the
  escalating reviewer may confirm or return it (also enforced by the API).
- finalize: refuses to run without a close or a confirmed escalation.
State is checkpointed after every node (thread_id = case_id), so a paused case
survives a restart. Every node, model call and tool call is written to the audit
log and traced (aml_agent/instrument.py).
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
from aml_agent.agent.casefile import build_case_file, resolve_accounts
from aml_agent.analysis.risk import RULE_BY_CODE
from aml_agent.instrument import (
    InstrumentedClient,
    InstrumentedProvider,
    NullAudit,
    audited_node,
)
from aml_agent.llm.base import ChatProvider
from aml_agent.schemas.case import (
    ANALYST_ACTIONS,
    SUPERVISOR_ACTIONS,
    Case,
    Decision,
    DraftReply,
    Evidence,
    GuidanceCitation,
    HypothesisReply,
)
from aml_agent.tools.client import GraphClient

EM_DASH = chr(0x2014)
MAX_TOOL_CONTENT_CHARS = 12_000
MAX_EVIDENCE_ROWS = 60  # the largest dev pattern has 30 transfers


@dataclass(frozen=True)
class Budget:
    max_steps: int = 12  # LLM turns in the investigate loop, per review round
    max_tool_calls: int = 20  # per review round
    max_tokens: int = 120_000  # input plus output, whole case
    max_review_rounds: int = 2  # "request more" rounds


class FinalizeRefused(RuntimeError):
    """Raised when finalize is reached without a close or a confirmed escalation."""


class FourEyesViolation(RuntimeError):
    """Raised when an escalation is confirmed by a non-supervisor or by the escalator."""


class CaseState(TypedDict, total=False):
    case_id: str
    alert: dict
    provider: str
    model: str
    prompt_version: str
    messages: list[dict]
    tool_log: list[dict]
    seen_tx_ids: list[int]
    seen_accounts: list[list]
    aliases: dict[str, list]
    evidence_rows: list[dict]
    case_graph: dict
    candidates: list[dict]
    risk: dict
    triggers: list[dict]
    case_file: str
    guidance: list[dict]
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
    verification: dict | None
    warnings: list[str]
    decisions: list[dict]
    review_round: int
    next_after_review: str
    next_after_supervisor: str
    status: str


GUIDANCE_PASSAGES = 4


def _normalize(text: str) -> str:
    """Compare quotes ignoring case, spacing, quote marks and dash styles."""
    for a, b in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"')):
        text = text.replace(a, b)
    text = re.sub(r"[\u2010-\u2015-]", "-", text)
    return " ".join(text.lower().split())


def _check_guidance(
    passages: list[dict], quotes: list, warnings: list[str]
) -> tuple[list[dict], list[GuidanceCitation]]:
    """Keep the citations whose quote appears word for word in a passage found for this
    case; report the others. Returns the passages (with what was cited) and the citations."""
    by_id = {p["passage_id"]: {**p, "quotes": []} for p in passages}
    citations: list[GuidanceCitation] = []
    for q in quotes:
        passage = by_id.get(q.passage_id)
        if passage is None:
            warnings.append(f"GUIDANCE_NOT_FOUND: {q.passage_id} was not among the passages found")
        elif _normalize(q.quote) not in _normalize(passage["text"]):
            warnings.append(f"GUIDANCE_QUOTE_NOT_FOUND: the quote from {q.passage_id} is not in it")
        else:
            passage["quotes"].append(q.quote)
            citations.append(
                GuidanceCitation(
                    chunk_id=q.passage_id,
                    source=passage["source"],
                    jurisdiction=passage["jurisdiction"],
                    quote_span=q.quote,
                )
            )
    return list(by_id.values()), citations


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


def _collect_accounts(obj: Any, out: list[list]) -> None:
    """Every (bank_id, account) a tool result mentions."""
    if isinstance(obj, dict):
        for bank_key, acct_key in (
            ("bank_id", "account"),
            ("from_bank", "from_account"),
            ("to_bank", "to_account"),
        ):
            if isinstance(obj.get(bank_key), int) and isinstance(obj.get(acct_key), str):
                pair = [obj[bank_key], obj[acct_key]]
                if pair not in out:
                    out.append(pair)
        for v in obj.values():
            _collect_accounts(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_accounts(v, out)


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


def build_graph(
    provider: ChatProvider,
    client: GraphClient,
    budget: Budget | None = None,
    audit=None,
    verifier=None,
):
    budget = budget or Budget()
    audit = audit or NullAudit()
    provider = InstrumentedProvider(provider, audit)
    client = InstrumentedClient(client, audit)

    async def triage(state: CaseState) -> CaseState:
        alert = state["alert"]
        case_file = await build_case_file(client, alert)
        return {
            "provider": provider.provider,
            "model": provider.model,
            "prompt_version": prompts.PROMPT_VERSION,
            "messages": [
                {"role": "system", "content": prompts.SYSTEM},
                {"role": "user", "content": prompts.triage_message(alert, case_file.text)},
            ],
            "tool_log": case_file.tool_log,
            "seen_tx_ids": case_file.seen_tx_ids,
            "seen_accounts": [list(a) for a in case_file.seen_accounts],
            "aliases": {k: list(v) for k, v in case_file.aliases.items()},
            "case_graph": case_file.graph,
            "candidates": case_file.candidates,
            "risk": case_file.risk,
            "triggers": case_file.triggers,
            "case_file": case_file.text,
            "evidence_rows": [],
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
        accounts = [list(a) for a in state.get("seen_accounts", [])]
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
                    _collect_accounts(result.content, accounts)
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
            "seen_accounts": accounts,
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

    async def collect_evidence(state: CaseState) -> CaseState:
        hypothesis = state.get("hypothesis") or {}
        warnings = list(state["warnings"])
        alert = state["alert"]
        seed = (alert["seed_bank"], alert["seed_account"])
        aliases = {k: (v[0], v[1]) for k, v in state.get("aliases", {}).items()}
        label = {acc: alias for alias, acc in aliases.items()}
        names = hypothesis.get("pattern_accounts") or []
        if hypothesis.get("pattern_hypothesis", "none") == "none" or not names:
            note = "No pattern was named, so code collected no evidence."
            return {
                "evidence_rows": [],
                "messages": [*state["messages"], {"role": "user", "content": note}],
            }
        known = {(a[0], a[1]) for a in state.get("seen_accounts", [])} | {seed}
        # "C1" stands for all accounts of code's pattern candidate C1.
        by_id = {c["id"]: c for c in state.get("candidates", [])}
        expanded: list = []
        for n in names:
            key = n.strip().split()[0] if isinstance(n, str) and n.strip() else None
            expanded.extend(by_id[key]["accounts"] if key in by_id else [n])
        accounts, problems = resolve_accounts(expanded, aliases, known)
        warnings.extend(f"EVIDENCE: {p}" for p in problems)
        if seed not in accounts:
            accounts.insert(0, seed)
        log = list(state["tool_log"])
        rows: list[dict] = []
        unconnected: list[str] = []
        if len(accounts) < 2:
            warnings.append("EVIDENCE: fewer than two usable accounts were named")
        else:
            args = {
                "accounts": [{"bank_id": b, "account": a} for b, a in accounts],
                "window_start": alert["window_start"],
                "window_end": alert["window_end"],
                "limit": 300,
            }
            result = await client.call("get_transfers_among", args)
            log.append(
                {
                    "by": "system",
                    "step": state["steps"],
                    "name": "get_transfers_among",
                    "arguments": args,
                    "ok": result.ok,
                    "error": result.error,
                    "duration_ms": round(result.duration_ms, 1),
                    "executed": True,
                }
            )
            if result.ok:
                rows = result.content["transfers"]
                if len(rows) > MAX_EVIDENCE_ROWS or result.content["truncated"]:
                    warnings.append(
                        f"EVIDENCE: {result.content['total_transfers']} transfers among the "
                        f"named accounts; the first {MAX_EVIDENCE_ROWS} are kept"
                    )
                    rows = rows[:MAX_EVIDENCE_ROWS]
                unconnected = [
                    label.get((u["bank_id"], u["account"]), f"{u['bank_id']}/{u['account']}")
                    for u in result.content["unconnected_accounts"]
                ]
                if unconnected:
                    warnings.append(
                        f"EVIDENCE: named accounts with no transfer to the others: {unconnected}"
                    )
            else:
                warnings.append(f"EVIDENCE: lookup failed: {result.error}")

        def name(bank: int, acct: str) -> str:
            return label.get((bank, acct), f"{bank}/{acct}")

        lines = [f"Evidence collected by code: {len(rows)} transfers among the accounts you named."]
        lines += [
            f"tx {r['tx_id']}: {name(r['from_bank'], r['from_account'])} -> "
            f"{name(r['to_bank'], r['to_account'])}, {r['amount_paid']} {r['currency_paid']}, "
            f"{r['ts']}"
            for r in rows
        ]
        if unconnected:
            lines.append(f"Named but not connected to the others: {', '.join(unconnected)}.")
        return {
            "evidence_rows": rows,
            "tool_log": log,
            "seen_tx_ids": list(
                dict.fromkeys([*state["seen_tx_ids"], *(r["tx_id"] for r in rows)])
            ),
            "warnings": warnings,
            "messages": [*state["messages"], {"role": "user", "content": "\n".join(lines)}],
        }

    async def draft(state: CaseState) -> CaseState:
        hypothesis = state.get("hypothesis")
        passages, log = await _find_guidance(state, hypothesis)
        parsed, update = await _structured(
            {**state, "tool_log": log},
            prompts.DRAFT + "\n" + prompts.guidance_block(passages),
            DraftReply,
        )
        warnings = list(state["warnings"])
        if parsed is None:
            warnings.append("MODEL_OUTPUT_INVALID: draft reply failed validation twice")
            reply = DraftReply(
                summary="The model did not produce a valid case draft.",
                recommended_action="needs_more_info",
                confidence="low",
                limitations="No valid model output; a human must investigate.",
            )
        else:
            reply = parsed
        evidence = [
            Evidence(
                tx_id=r["tx_id"],
                from_bank=str(r["from_bank"]),
                from_account=r["from_account"],
                to_bank=str(r["to_bank"]),
                to_account=r["to_account"],
                amount_paid=r["amount_paid"],
                currency_paid=r["currency_paid"],
                timestamp=r["ts"],
            )
            for r in state.get("evidence_rows", [])
        ]
        cited = [e.tx_id for e in evidence]
        guidance, citations = _check_guidance(passages, reply.guidance_citations, warnings)
        case = Case(
            case_id=state["case_id"],
            pattern_hypothesis=hypothesis["pattern_hypothesis"] if hypothesis else "none",
            summary=_strip_em_dash(reply.summary, warnings, "summary"),
            evidence=evidence,
            recommended_action=reply.recommended_action,
            confidence=reply.confidence,
            limitations=_strip_em_dash(reply.limitations, warnings, "limitations"),
            guidance_citations=citations,
        )
        if hypothesis is None:
            warnings.append("pattern_hypothesis defaulted to none because the hypothesis failed")
        return {
            **update,
            "tool_log": log,
            "cited_tx_ids": cited,
            "guidance": guidance,
            "case": case.model_dump(),
            "warnings": warnings,
            "status": "pending_review",
        }

    async def _find_guidance(state: CaseState, hypothesis: dict | None) -> tuple[list, list]:
        """Guidance passages for the typology and red flags, found by code through MCP."""
        risk = state.get("risk") or {}
        codes = [
            *((risk.get("subject") or {}).get("rules") or []),
            *((risk.get("top_counterparty") or {}).get("rules") or []),
        ]
        flags = [RULE_BY_CODE[c].title for c in dict.fromkeys(codes) if c in RULE_BY_CODE]
        pattern = hypothesis["pattern_hypothesis"] if hypothesis else None
        args = {"query": prompts.guidance_query(pattern, flags), "k": GUIDANCE_PASSAGES}
        result = await client.call("search_guidance", args)
        log = [
            *state["tool_log"],
            {
                "by": "system",
                "step": state["steps"],
                "name": "search_guidance",
                "arguments": args,
                "ok": result.ok,
                "error": result.error,
                "duration_ms": round(result.duration_ms, 1),
                "executed": True,
            },
        ]
        passages = (result.content or {}).get("passages", []) if result.ok else []
        return passages, log

    async def verify(state: CaseState) -> CaseState:
        warnings = list(state["warnings"])
        if verifier is None:
            warnings.append("NOT_VERIFIED: no citation verifier configured")
            return {"verification": None, "warnings": warnings}
        result = verifier.verify_case(
            state["case"],
            cited_tx_ids=state.get("cited_tx_ids", []),
            seen_tx_ids=state["seen_tx_ids"],
        )
        return {"verification": result.as_dict(), "warnings": [*warnings, *result.warnings()]}

    async def human_review(state: CaseState) -> CaseState:
        raw = interrupt(
            {
                "case_id": state["case_id"],
                "case": state["case"],
                "verification": state.get("verification"),
                "warnings": state["warnings"],
            }
        )
        decision = Decision.model_validate(raw)
        if decision.action not in ANALYST_ACTIONS:
            raise ValueError(f"{decision.action} is not an analyst decision")
        decisions = [*state["decisions"], decision.model_dump(mode="json")]
        if decision.action == "close":
            return {"decisions": decisions, "next_after_review": "finalize"}
        if decision.action == "escalate":
            return {"decisions": decisions, "next_after_review": "supervisor_review"}
        if state["review_round"] >= budget.max_review_rounds:
            warnings = [
                *state["warnings"],
                "more investigation was requested but the review-round limit is reached; "
                "close or escalate",
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

    async def supervisor_review(state: CaseState) -> CaseState:
        raw = interrupt({"case_id": state["case_id"], "awaiting": "supervisor"})
        decision = Decision.model_validate(raw)
        escalator = next(
            (d["reviewer"] for d in reversed(state["decisions"]) if d["action"] == "escalate"),
            None,
        )
        if decision.action not in SUPERVISOR_ACTIONS:
            raise ValueError(f"{decision.action} is not a supervisor decision")
        if decision.role != "supervisor" or decision.reviewer == escalator:
            raise FourEyesViolation(
                f"case {state.get('case_id')}: an escalation needs a different supervisor"
            )
        decisions = [*state["decisions"], decision.model_dump(mode="json")]
        if decision.action == "confirm_escalation":
            return {"decisions": decisions, "next_after_supervisor": "finalize"}
        return {"decisions": decisions, "next_after_supervisor": "human_review"}

    async def finalize(state: CaseState) -> CaseState:
        decisions = state.get("decisions") or []
        last = decisions[-1] if decisions else None
        if not last or last["action"] not in ("close", "confirm_escalation"):
            raise FinalizeRefused(
                f"case {state.get('case_id')}: finalize needs a close or a confirmed escalation"
            )
        return {"status": "closed" if last["action"] == "close" else "escalated"}

    g = StateGraph(CaseState)
    nodes = {
        "triage": triage,
        "agent": agent,
        "tools": tools,
        "hypothesize": hypothesize,
        "collect_evidence": collect_evidence,
        "draft": draft,
        "verify": verify,
        "human_review": human_review,
        "supervisor_review": supervisor_review,
        "finalize": finalize,
    }
    for name, fn in nodes.items():
        g.add_node(name, audited_node(name, fn, audit))
    g.add_edge(START, "triage")
    g.add_edge("triage", "agent")
    g.add_conditional_edges("agent", after_agent, ["tools", "hypothesize"])
    g.add_conditional_edges("tools", after_tools, ["agent", "hypothesize"])
    g.add_edge("hypothesize", "collect_evidence")
    g.add_edge("collect_evidence", "draft")
    g.add_edge("draft", "verify")
    g.add_edge("verify", "human_review")
    g.add_conditional_edges(
        "human_review",
        lambda s: s["next_after_review"],
        ["finalize", "agent", "human_review", "supervisor_review"],
    )
    g.add_conditional_edges(
        "supervisor_review",
        lambda s: s["next_after_supervisor"],
        ["finalize", "human_review"],
    )
    g.add_edge("finalize", END)
    return g, finalize


def compile_graph(provider, client, checkpointer, budget=None, audit=None, verifier=None):
    g, _ = build_graph(provider, client, budget, audit, verifier)
    return g.compile(checkpointer=checkpointer)
