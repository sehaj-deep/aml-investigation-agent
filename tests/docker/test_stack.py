"""Checks against the running Docker Compose stack (not run in CI)."""

import json
import subprocess

import pytest

pytestmark = pytest.mark.docker


def _compose(*args: str) -> str:
    return subprocess.run(
        ["docker", "compose", *args], check=True, capture_output=True, text=True
    ).stdout


def test_postgres_has_pgvector():
    out = _compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "aml",
        "-d",
        "aml",
        "-tAc",
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'",
    )
    assert out.strip()


def test_neighbor_lookup_p95_under_one_second_in_docker():
    out = _compose("--profile", "bench", "run", "--rm", "bench")
    result = json.loads(out.strip().splitlines()[-1])
    assert result["lookups"] == 1000
    assert result["p95_ms"] < 1000
