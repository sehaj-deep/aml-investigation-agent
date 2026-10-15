"""Load (or refresh) the monitoring alert queue into Postgres.

    python scripts/load_alerts.py

Reads data/alert_queue/alerts.jsonl, written by scripts/train_detection.py. The API also
loads it at startup when the alerts table is empty.
"""

from __future__ import annotations

import asyncio
import os

from aml_agent import store
from aml_agent.alerts.io import read_queue


async def main() -> None:
    async with store.make_pool() as pool:
        await store.init_schema(pool)
        n = await store.load_alerts(pool, (a.model_dump(mode="json") for a in read_queue()))
    if n == 0:
        raise SystemExit("no alert queue found; run scripts/train_detection.py first")
    print(f"loaded {n} alerts")


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
