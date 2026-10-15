"""A lost tool connection is retried, not reported as a failed review."""

from __future__ import annotations

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from aml_agent.worker import ToolConnectionLost, is_connection_lost


def mcp_error(text: str = "Session terminated") -> McpError:
    return McpError(ErrorData(code=-32000, message=text))


@pytest.mark.parametrize(
    "exc",
    [
        mcp_error(),
        ToolConnectionLost("gone"),
        ConnectionResetError("reset"),
        BaseExceptionGroup("task group", [ValueError("x"), mcp_error()]),
        type("ClosedResourceError", (Exception,), {})(),
        type("ConnectError", (Exception,), {})(),
    ],
    ids=["mcp-session", "lost", "connection-reset", "exception-group", "anyio", "httpx"],
)
def test_connection_failures_are_recognized(exc):
    assert is_connection_lost(exc)


def test_wrapped_connection_failure_is_recognized():
    try:
        try:
            raise mcp_error()
        except McpError as inner:
            raise RuntimeError("node failed") from inner
    except RuntimeError as exc:
        assert is_connection_lost(exc)


@pytest.mark.parametrize(
    "exc",
    [ValueError("bad schema"), FileNotFoundError("missing parquet"), KeyError("x")],
    ids=["value", "missing-file", "key"],
)
def test_case_failures_are_not_connection_failures(exc):
    assert not is_connection_lost(exc)
