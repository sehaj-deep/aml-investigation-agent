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

from aml_agent.guidance.search import MAX_K, GuidanceSearch
from aml_agent.tools.graph import GraphTools

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

_tools: GraphTools | None = None


def tools() -> GraphTools:
    global _tools
    if _tools is None:
        _tools = GraphTools()
    return _tools


_guidance: GuidanceSearch | None = None


def guidance() -> GuidanceSearch:
    global _guidance
    if _guidance is None:
        _guidance = GuidanceSearch()
    return _guidance


def build_server(host: str = "127.0.0.1", port: int = 8001) -> FastMCP:
    mcp = FastMCP(
        "aml-graph",
        instructions=(
            "Read-only tools over a synthetic transaction graph. Accounts are identified by "
            "(bank_id, account). Amounts are per currency; never add amounts in different "
            "currencies. Times are ISO 8601 without time zone. Data runs from 2022-09-01 to "
            "2022-09-18. search_guidance searches public AML guidance (FinCEN, FFIEC)."
        ),
        host=host,
        port=port,
    )

    @mcp.tool(annotations=READ_ONLY)
    def search_guidance(query: str, k: int = 5) -> dict:
        """Search public AML guidance (FFIEC red flags, FinCEN advisories on funnel accounts
        and shell companies, FinCEN SAR narrative guidance) for passages about a typology,
        red flag or reporting question. Returns up to k passages (1 to 8) with passage_id,
        source, where (page or section), url and text. Cite a passage by its passage_id and
        quote its exact words."""
        query = " ".join(query.split())
        if not 3 <= len(query) <= 300:
            raise ValueError("query must be 3 to 300 characters")
        if not 1 <= k <= MAX_K:
            raise ValueError(f"k must be 1 to {MAX_K}")
        try:
            return guidance().search(query, k)
        except Exception as exc:  # store not set up or not reachable: say so, do not crash
            return {"mode": "unavailable", "passages": [], "error": type(exc).__name__}

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
        direction: Literal["in", "out", "both", "forward", "backward"] = "both",
        limit: int = 25,
        include_self_transfers: bool = False,
    ) -> dict:
        """Counterparties of an account in a time window (most active first). direction:
        "in" (who sent money to it), "out" (who it paid) or "both". Each counterparty also
        shows their_senders and their_receivers: how many distinct accounts it is paid by
        and pays in the window (a high number marks a hub). Each comes with
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
        direction: Literal["forward", "backward", "out", "in"] = "forward",
        hops: int = 2,
        max_edges: int = 100,
    ) -> dict:
        """Follow money out of an account ("forward" or "out") or back to where it came from
        ("backward" or "in") for up to 8 hops, keeping
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
    def get_transfers_among(
        accounts: list[dict],
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        limit: int = 200,
    ) -> dict:
        """Transfers whose sender and receiver are BOTH in a group of 2 to 30 accounts, each
        given as {"bank_id": int, "account": str}. Use it once you know which accounts form
        the pattern: it shows the pattern's own transfers without their other activity, and
        lists group accounts that have no transfer with the rest of the group."""
        return tools().get_transfers_among(
            accounts=accounts, window_start=window_start, window_end=window_end, limit=limit
        )

    @mcp.tool(annotations=READ_ONLY)
    def get_account_behavior(
        bank_id: int,
        account: str,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> dict:
        """Behavioral red flags for one account in a review period: whether it both receives
        and pays, currency conversion, share of new and one-time counterparties, how
        concentrated its activity is in the period, and how quickly incoming funds move
        on; plus the risk rules (R1 to R6) these fire and the account's rule score."""
        return tools().get_account_behavior(
            bank_id=bank_id, account=account, window_start=window_start, window_end=window_end
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
