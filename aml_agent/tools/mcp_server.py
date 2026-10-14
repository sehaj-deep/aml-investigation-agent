"""MCP server exposing the read-only graph tools. The agent's only route to data.

Run:  python -m aml_agent.tools.mcp_server              (stdio)
      python -m aml_agent.tools.mcp_server --http       (streamable HTTP on MCP_PORT)
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from aml_agent.tools.graph import GraphTools

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

_tools: GraphTools | None = None


def tools() -> GraphTools:
    global _tools
    if _tools is None:
        _tools = GraphTools()
    return _tools


def build_server(host: str = "127.0.0.1", port: int = 8001) -> FastMCP:
    mcp = FastMCP(
        "aml-graph",
        instructions=(
            "Read-only tools over a synthetic transaction graph. Accounts are identified by "
            "(bank_id, account). Amounts are per currency; never add amounts in different "
            "currencies. Times are ISO 8601 without time zone."
        ),
        host=host,
        port=port,
    )

    @mcp.tool(annotations=READ_ONLY)
    def get_account_summary(
        bank_id: int,
        account: str,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> dict:
        """Per-currency sent and received counts and totals for one account in a time
        window, plus the number of counterparties and the first and last transaction time.
        Self-transfers are excluded and counted separately."""
        return tools().get_account_summary(
            bank_id=bank_id, account=account, window_start=window_start, window_end=window_end
        )

    @mcp.tool(annotations=READ_ONLY)
    def get_neighbors(
        bank_id: int,
        account: str,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        direction: Literal["in", "out", "both"] = "both",
        limit: int = 25,
        include_self_transfers: bool = False,
    ) -> dict:
        """Counterparties of an account in a time window (most active first), each with
        per-currency totals, first and last time and up to 20 tx_ids. At most 100
        counterparties."""
        return tools().get_neighbors(
            bank_id=bank_id,
            account=account,
            window_start=window_start,
            window_end=window_end,
            direction=direction,
            limit=limit,
            include_self_transfers=include_self_transfers,
        )

    @mcp.tool(annotations=READ_ONLY)
    def trace_funds(
        bank_id: int,
        account: str,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        direction: Literal["forward", "backward"] = "forward",
        hops: int = 2,
        max_edges: int = 100,
    ) -> dict:
        """Follow money from (forward) or to (backward) an account for up to 4 hops, keeping
        time order. Returns the transfers found, with hop numbers. At most 300 edges and 20
        transfers per account per hop."""
        return tools().trace_funds(
            bank_id=bank_id,
            account=account,
            window_start=window_start,
            window_end=window_end,
            direction=direction,
            hops=hops,
            max_edges=max_edges,
        )

    @mcp.tool(annotations=READ_ONLY)
    def get_transactions(tx_ids: list[int]) -> dict:
        """Full records for up to 100 transactions by tx_id."""
        return tools().get_transactions(tx_ids=tx_ids)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP")
    args = parser.parse_args()
    if args.http:
        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8001"))
        build_server(host, port).run("streamable-http")
    else:
        build_server().run("stdio")


if __name__ == "__main__":
    main()
