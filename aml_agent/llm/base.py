"""Provider-neutral chat types.

Messages are plain dicts so they serialize cleanly into LangGraph checkpoints:
    {"role": "system" | "user" | "assistant" | "tool", "content": str,
     "tool_calls": [...] (assistant only), "tool_call_id": str (tool only),
     "name": str (tool only)}
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Tool calls the provider could not parse (bad JSON arguments and similar).
    invalid_tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0

    def as_message(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [
                {"id": c.id, "name": c.name, "arguments": c.arguments} for c in self.tool_calls
            ]
        return msg


class ChatProvider(Protocol):
    provider: str
    model: str

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict] | None = None
    ) -> ChatResponse: ...


def get_provider() -> ChatProvider:
    """Provider from the environment: LLM_PROVIDER (ollama | scripted) and LLM_MODEL."""
    name = os.environ.get("LLM_PROVIDER", "ollama")
    if name == "ollama":
        from aml_agent.llm.ollama import OllamaProvider

        return OllamaProvider(
            model=os.environ.get("LLM_MODEL", "gpt-oss:20b-cloud"),
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    if name == "scripted":
        from aml_agent.llm.scripted import ScriptedProvider

        return ScriptedProvider.from_env()
    raise ValueError(f"unknown LLM_PROVIDER {name!r}")
