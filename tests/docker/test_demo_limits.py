"""Public-demo usage limits on the real Postgres (database aml_test)."""

from __future__ import annotations

import asyncio
import sys

import psycopg
import pytest

from aml_agent import demo, store

pytestmark = pytest.mark.docker

TEST_DB = "aml_test"


def run(coro_fn):
    async def main():
        url = store.database_url().rsplit("/", 1)[0] + f"/{TEST_DB}"
        try:
            async with store.make_pool(url) as pool:
                await demo.init(pool)
                async with pool.connection() as conn:
                    await conn.execute("TRUNCATE demo_usage")
                return await coro_fn(pool)
        except psycopg.OperationalError as exc:
            pytest.skip(f"Postgres not reachable: {exc}")

    if sys.platform == "win32":  # psycopg async needs the selector event loop on Windows
        return asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(main())


def test_limits_apply_per_visitor_and_per_site(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setitem(demo.LIMITS, "copilot", (2, 3))

    async def steps(pool):
        await demo.use(pool, "copilot", "visitor-a")
        await demo.use(pool, "copilot", "visitor-a")
        with pytest.raises(demo.LimitReached, match="your 2 copilot questions"):
            await demo.use(pool, "copilot", "visitor-a")
        await demo.use(pool, "copilot", "visitor-b")
        with pytest.raises(demo.LimitReached, match="daily limit of 3 copilot questions"):
            await demo.use(pool, "copilot", "visitor-c")
        return await demo.status(pool, "visitor-b")

    status = run(steps)
    assert status["demo"] is True and status["left"]["copilot"] == 0


def test_limits_are_off_outside_the_demo(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setitem(demo.LIMITS, "copilot", (1, 1))

    async def steps(pool):
        for _ in range(3):
            await demo.use(pool, "copilot", "visitor-a")
        return await demo.status(pool, "visitor-a")

    assert run(steps) == {"demo": False}


def test_visitor_ids_do_not_store_addresses():
    vid = demo.visitor_id("203.0.113.7")
    assert "203.0.113.7" not in vid and len(vid) == 16


def test_forged_forwarding_entries_do_not_change_the_visitor(monkeypatch):
    monkeypatch.setenv("DEMO_TRUSTED_PROXY_HOPS", "1")
    real = {"x-forwarded-for": "203.0.113.7, 10.0.0.1"}  # visitor, then our proxy
    forged = {"x-forwarded-for": "198.51.100.1, 203.0.113.7, 10.0.0.1"}
    assert demo.client_address(real, "10.0.0.9") == "203.0.113.7"
    assert demo.client_address(forged, "10.0.0.9") == "203.0.113.7"
    assert demo.client_address({}, "10.0.0.9") == "10.0.0.9"
    monkeypatch.setenv("DEMO_TRUSTED_PROXY_HOPS", "2")
    two = {"x-forwarded-for": "198.51.100.1, 203.0.113.7, 172.16.0.1, 10.0.0.1"}
    assert demo.client_address(two, None) == "203.0.113.7"
