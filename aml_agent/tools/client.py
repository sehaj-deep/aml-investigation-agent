"""MCP client used by the agent. The agent calls tools only through this client.

Connects over stdio (spawns the server as a subprocess) when MCP_URL is unset,
or over streamable HTTP to the mcp-graph service when MCP_URL is set.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


@dataclass
class ToolResult:
    name: str
    arguments: dict[str, Any]
    ok: bool
    content: Any
    error: str | None
    duration_ms: float


class GraphClient:
    def __init__(self, session: ClientSession):
        self.session = session
        self._specs: list[dict] | None = None

    async def tool_specs(self) -> list[dict]:
        """Tool definitions in the OpenAI function format the chat models accept."""
        if self._specs is None:
            listed = await self.session.list_tools()
            self._specs = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema,
                    },
                }
                for t in listed.tools
            ]
        return self._specs

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        start = time.perf_counter()
        result = await self.session.call_tool(name, arguments)
        duration = (time.perf_counter() - start) * 1000
        text = "".join(getattr(c, "text", "") for c in result.content)
        if result.isError:
            return ToolResult(name, arguments, False, None, text, duration)
        content = result.structuredContent
        if content is None:
            content = json.loads(text) if text else None
        elif set(content) == {"result"}:
            content = content["result"]
        return ToolResult(name, arguments, True, content, None, duration)


@asynccontextmanager
async def connect_graph(env: dict[str, str] | None = None) -> AsyncIterator[GraphClient]:
    url = os.environ.get("MCP_URL")
    if url:
        async with (
            streamable_http_client(url) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            yield GraphClient(session)
    else:
        if sys.platform == "win32" and isinstance(
            asyncio.get_running_loop(), asyncio.SelectorEventLoop
        ):
            # psycopg async needs the selector loop on Windows, which cannot spawn
            # subprocesses. Run the server with --http and set MCP_URL instead.
            raise RuntimeError("stdio MCP is unavailable on a Windows selector loop; set MCP_URL")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "aml_agent.tools.mcp_server"],
            env={**os.environ, **(env or {})},
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            yield GraphClient(session)
