"""Paths and settings, read from the environment (and a local .env)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

TRANS_FILE = "HI-Small_Trans.csv"
ACCOUNTS_FILE = "HI-Small_accounts.csv"
PATTERNS_FILE = "HI-Small_Patterns.txt"


def data_dir() -> Path:
    """Folder with the raw HI-Small files (outside the repo)."""
    value = os.environ.get("AML_DATA_DIR")
    if not value:
        raise RuntimeError("AML_DATA_DIR is not set; copy .env.example to .env")
    return Path(value)


def parquet_dir() -> Path:
    """Folder with the converted Parquet tables (gitignored)."""
    path = Path(os.environ.get("PARQUET_DIR", "data/parquet"))
    return path if path.is_absolute() else REPO_ROOT / path


def alert_queue_dir() -> Path:
    """Folder with the monitoring alert queue (gitignored). It holds no labels, so the
    API can mount it; the model and labels stay in data/detection."""
    path = Path(os.environ.get("ALERT_QUEUE_DIR", "data/alert_queue"))
    return path if path.is_absolute() else REPO_ROOT / path


def table_path(name: str) -> Path:
    return parquet_dir() / f"{name}.parquet"
