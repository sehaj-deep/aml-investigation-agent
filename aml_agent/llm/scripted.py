"""Deterministic scripted provider for tests, CI fixtures and harness checks.

It never calls a model. It reads the conversation and acts like a minimal
investigator, so the whole workflow (tools, budgets, approval, checkpoints) can
be exercised without quota. Numbers produced with it are harness results, not
model results (PRD section 9, rule 7).

Policies (LLM_SCRIPT_POLICY):
  basic      neighbors, then a 2-hop forward trace, then stop
  loop       keeps calling tools forever (tests the step cap)
  bad_tool   first an unknown tool and malformed arguments, then basic
  bad_json   first hypothesis reply is not JSON, then valid
  emdash     the drafted summary contains an em dash (tests the guard)
  none       concludes "none" and recommends closing
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from typing import Any

from aml_agent.llm.base import ChatResponse, ToolCall

ALERT_RE = re.compile(r"<alert>\s*(\{.*?\})\s*</alert>", re.S)
EM_DASH = chr(0x2014)


def _alert(messages: list[dict]) -> dict:
    for m in messages:
        if m["role"] == "user" and (match := ALERT_RE.search(m["content"])):
            return json.loads(match.group(1))
    raise ValueError("no alert in conversation")


def _seen_tx_ids(messages: list[dict]) -> list[int]:
    seen: list[int] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "tx_id" and isinstance(v, int):
                    seen.append(v)
                elif k == "tx_ids" and isinstance(v, list):
                    seen.extend(x for x in v if isinstance(x, int))
                else:
                    walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for m in messages:
        if m["role"] == "tool":
            with contextlib.suppress(json.JSONDecodeError):
                walk(json.loads(m["content"]))
    return list(dict.fromkeys(seen))


def _phase(messages: list[dict]) -> str:
    """The task of the latest instruction (a schema retry keeps the task it retries)."""
    for m in reversed(messages):
        if m["role"] != "user":
            continue
        if "TASK: HYPOTHESIZE" in m["content"]:
            return "hypothesize"
        if "TASK: DRAFT" in m["content"]:
            return "draft"
        if "could not be parsed" not in m["content"]:
            return "investigate"
    return "investigate"


class ScriptedProvider:
    provider = "scripted"

    def __init__(self, policy: str = "basic"):
        self.policy = policy
        self.model = f"scripted-{policy}"
        self.calls = 0
        self._bad_json_sent = False

    @classmethod
    def from_env(cls) -> ScriptedProvider:
        return cls(os.environ.get("LLM_SCRIPT_POLICY", "basic"))

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict] | None = None
    ) -> ChatResponse:
        self.calls += 1
        phase = _phase(messages)
        if phase == "investigate":
            resp = self._investigate(messages)
        elif phase == "hypothesize":
            resp = self._hypothesize(messages)
        else:
            resp = self._draft(messages)
        prompt_chars = sum(len(m.get("content") or "") for m in messages)
        resp.input_tokens = prompt_chars // 4
        resp.output_tokens = max(1, len(resp.content) // 4) + 20 * len(resp.tool_calls)
        return resp

    def _call(self, name: str, args: dict) -> ChatResponse:
        return ChatResponse(content="", tool_calls=[ToolCall(f"call_{self.calls}", name, args)])

    def _investigate(self, messages: list[dict]) -> ChatResponse:
        alert = _alert(messages)
        seed = {
            "bank_id": alert["seed_bank"],
            "account": alert["seed_account"],
            "window_start": alert["window_start"],
            "window_end": alert["window_end"],
        }
        n_tool = sum(1 for m in messages if m["role"] == "tool")
        if self.policy == "loop":
            return self._call("get_neighbors", {**seed, "limit": 5})
        if self.policy == "bad_tool":
            if n_tool == 0:
                return self._call("delete_everything", {"bank_id": 1})
            if n_tool == 1:
                return self._call("get_neighbors", {**seed, "bank_id": "not-a-number"})
            n_tool -= 2
        if n_tool == 0:
            return self._call("get_neighbors", {**seed, "direction": "both", "limit": 10})
        if n_tool == 1:
            return self._call("trace_funds", {**seed, "direction": "forward", "hops": 2})
        return ChatResponse(content="Investigation complete.")

    def _hypothesize(self, messages: list[dict]) -> ChatResponse:
        if self.policy == "bad_json" and not self._bad_json_sent:
            self._bad_json_sent = True
            return ChatResponse(content="I think this is a fan-out pattern.")
        seen = _seen_tx_ids(messages)
        pattern = "none" if self.policy == "none" else "fan-out"
        return ChatResponse(
            content=json.dumps(
                {
                    "pattern_hypothesis": pattern,
                    "rationale": "Scripted rationale based on the counterparties found.",
                    "key_tx_ids": seen[:3],
                }
            )
        )

    def _draft(self, messages: list[dict]) -> ChatResponse:
        seen = _seen_tx_ids(messages)
        dash = f" {EM_DASH} " if self.policy == "emdash" else ", "
        none = self.policy == "none"
        return ChatResponse(
            content=json.dumps(
                {
                    "summary": f"Scripted summary{dash}the seed account was reviewed.",
                    "evidence_tx_ids": [] if none else seen[:5],
                    "recommended_action": "close" if none else "escalate",
                    "confidence": "low",
                    "limitations": "Scripted output for harness testing; not a model result.",
                }
            )
        )
