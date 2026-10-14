"""Test helpers: start the MCP server over HTTP and worker processes."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_port(port: int, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"nothing listening on {port}")


@contextmanager
def mcp_http_server(env: dict[str, str] | None = None) -> Iterator[str]:
    """Run the graph MCP server over HTTP; yields its URL."""
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "aml_agent.tools.mcp_server", "--http"],
        env={**os.environ, **(env or {}), "MCP_HOST": "127.0.0.1", "MCP_PORT": str(port)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_port(port)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        proc.wait(timeout=30)
