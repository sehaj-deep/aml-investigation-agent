"""Ollama provider (cloud models through the local Ollama app, free tier).

Retries rate-limit and transient errors with exponential backoff.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama

from aml_agent.llm.base import ChatResponse, ToolCall

MAX_RETRIES = 5
RETRYABLE = ("429", "rate limit", "too many requests", "503", "502", "timeout", "temporarily")


def _to_langchain(messages: list[dict[str, Any]]) -> list:
    out = []
    for m in messages:
        role = m["role"]
        if role == "system":
            out.append(SystemMessage(m["content"]))
        elif role == "user":
            out.append(HumanMessage(m["content"]))
        elif role == "assistant":
            calls = [
                {"id": c["id"], "name": c["name"], "args": c["arguments"]}
                for c in m.get("tool_calls", [])
            ]
            out.append(AIMessage(m["content"], tool_calls=calls))
        elif role == "tool":
            out.append(ToolMessage(m["content"], tool_call_id=m["tool_call_id"], name=m["name"]))
    return out


class OllamaProvider:
    provider = "ollama"

    def __init__(self, model: str, base_url: str, temperature: float = 0.0, seed: int = 7):
        self.model = model
        self._llm = ChatOllama(model=model, base_url=base_url, temperature=temperature, seed=seed)

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict] | None = None
    ) -> ChatResponse:
        llm = self._llm.bind_tools(tools) if tools else self._llm
        lc_messages = _to_langchain(messages)
        delay = 2.0
        for attempt in range(MAX_RETRIES):
            start = time.perf_counter()
            try:
                msg: AIMessage = await llm.ainvoke(lc_messages)
                break
            except Exception as exc:  # provider errors are not typed consistently
                text = str(exc).lower()
                if attempt == MAX_RETRIES - 1 or not any(k in text for k in RETRYABLE):
                    raise
                await asyncio.sleep(delay)
                delay *= 2
        latency = (time.perf_counter() - start) * 1000
        usage = msg.usage_metadata or {}
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        return ChatResponse(
            content=content,
            tool_calls=[
                ToolCall(id=c.get("id") or f"call_{i}", name=c["name"], arguments=c["args"])
                for i, c in enumerate(msg.tool_calls)
            ],
            invalid_tool_calls=len(msg.invalid_tool_calls),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            latency_ms=latency,
        )
