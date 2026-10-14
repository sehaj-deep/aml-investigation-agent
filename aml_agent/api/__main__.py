"""Run the API: python -m aml_agent.api  (API_HOST, API_PORT)."""

from __future__ import annotations

import asyncio
import os

import uvicorn


def main() -> None:
    if os.name == "nt":
        # psycopg async needs the selector event loop on Windows.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run(
        "aml_agent.api.app:app",
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8000")),
        loop="none",
    )


if __name__ == "__main__":
    main()
