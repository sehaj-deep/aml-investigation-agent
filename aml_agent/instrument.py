"""Audit and tracing around the workflow, without changing the nodes.

- `audited_node` wraps a node: records its start, its state delta (or interrupt or
  failure) and runs it inside a span.
- `InstrumentedProvider` and `InstrumentedClient` wrap the model and the MCP client:
  each call becomes an audit event and a span.
The current case and node are carried in context variables.
"""

from __future__ import annotations

import contextvars
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.errors import GraphInterrupt
from opentelemetry import trace

from aml_agent.agent import prompts
from aml_agent.audit import AuditSink, state_delta
from aml_agent.llm.base import ChatResponse
from aml_agent.tools.client import ToolResult

current_case: contextvars.ContextVar[str | None] = contextvars.ContextVar("case", default=None)
current_node: contextvars.ContextVar[str | None] = contextvars.ContextVar("node", default=None)

tracer = trace.get_tracer("aml_agent")


class NullAudit:
    async def emit(self, case_id, event_type, payload, actor="agent") -> None:
        return None


def audited_node(name: str, fn: Callable[[dict], Awaitable[dict]], audit: AuditSink):
    async def wrapped(state: dict) -> dict:
        case_id = state["case_id"]
        token_c = current_case.set(case_id)
        token_n = current_node.set(name)
        try:
            with tracer.start_as_current_span(f"node.{name}") as span:
                span.set_attribute("case_id", case_id)
                if name == "triage":
                    await audit.emit(
                        case_id,
                        "case_started",
                        {"input": {"case_id": case_id, "alert": state["alert"]}},
                    )
                await audit.emit(case_id, "node_started", {"node": name})
                try:
                    update = await fn(state)
                except GraphInterrupt:
                    await audit.emit(case_id, "node_interrupted", {"node": name})
                    raise
                except Exception as exc:
                    await audit.emit(
                        case_id,
                        "node_failed",
                        {"node": name, "error": f"{type(exc).__name__}: {exc}"},
                    )
                    span.record_exception(exc)
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                    raise
                await audit.emit(
                    case_id, "node_finished", {"node": name, "delta": state_delta(state, update)}
                )
                return update
        finally:
            current_node.reset(token_n)
            current_case.reset(token_c)

    return wrapped


class InstrumentedProvider:
    def __init__(self, inner, audit: AuditSink):
        self.inner = inner
        self.audit = audit
        self.provider = inner.provider
        self.model = inner.model

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResponse:
        with tracer.start_as_current_span("model.chat") as span:
            span.set_attribute("llm.provider", self.provider)
            span.set_attribute("llm.model", self.model)
            span.set_attribute("llm.prompt_version", prompts.PROMPT_VERSION)
            resp = await self.inner.chat(messages, tools)
            span.set_attribute("llm.input_tokens", resp.input_tokens)
            span.set_attribute("llm.output_tokens", resp.output_tokens)
            span.set_attribute("llm.tool_calls", len(resp.tool_calls))
        case_id = current_case.get()
        if case_id:
            await self.audit.emit(
                case_id,
                "model_call",
                {
                    "node": current_node.get(),
                    "provider": self.provider,
                    "model": self.model,
                    "prompt_version": prompts.PROMPT_VERSION,
                    "n_messages": len(messages),
                    "tools_offered": [t["function"]["name"] for t in tools or []],
                    "input_tokens": resp.input_tokens,
                    "output_tokens": resp.output_tokens,
                    "latency_ms": round(resp.latency_ms, 1),
                    "invalid_tool_calls": resp.invalid_tool_calls,
                    "reply": resp.as_message(),
                },
            )
        return resp


class InstrumentedClient:
    def __init__(self, inner, audit: AuditSink):
        self.inner = inner
        self.audit = audit

    async def tool_specs(self) -> list[dict]:
        return await self.inner.tool_specs()

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        with tracer.start_as_current_span(f"tool.{name}") as span:
            span.set_attribute("tool.name", name)
            result = await self.inner.call(name, arguments)
            span.set_attribute("tool.ok", result.ok)
            span.set_attribute("tool.duration_ms", result.duration_ms)
        case_id = current_case.get()
        if case_id:
            await self.audit.emit(
                case_id,
                "tool_call",
                {
                    "node": current_node.get(),
                    "name": name,
                    "arguments": arguments,
                    "ok": result.ok,
                    "error": result.error,
                    "duration_ms": round(result.duration_ms, 1),
                    "result": result.content,
                },
            )
        return result
