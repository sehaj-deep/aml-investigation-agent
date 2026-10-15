"""Assemble the public demo (a Hugging Face Space) and optionally upload it.

    python scripts/build_space.py                    build into data/space only
    python scripts/build_space.py --upload           build, then create or update the Space

The Space is one Docker container (deploy/space/). This script copies the code and the
UI, and exports from the local stack:
- the demo database: the reviewed cases with everything a visitor needs (alerts, case
  files, assessments, decisions, copilot answers, SAR drafts, audit log, workflow
  checkpoints) and the guidance passages;
- the data slice: every transaction touching an account that appears in a demo case
  (tool columns only, no laundering labels), under the dataset's CDLA-Sharing licence.

The build folder is under data/ (gitignored): the data slice never goes to GitHub.
Uploading uses the Hugging Face login stored on this machine (hf auth login).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import duckdb
import psycopg

from aml_agent import store
from aml_agent.data.tooldb import tool_db_path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "space"
SPACE_ID = "sehajdeep490/aml-investigation-agent"
HF = Path.home() / ".hf-cli" / "Scripts" / "hf.exe"
SKIP = {"__pycache__", "node_modules", "dist", ".vite"}

EXPORTS = {
    "alerts": "SELECT * FROM alerts WHERE alert_id IN "
    "(SELECT alert_id FROM cases WHERE case_id = ANY(%(ids)s))",
    "cases": "SELECT * FROM cases WHERE case_id = ANY(%(ids)s)",
    "decisions": "SELECT * FROM decisions WHERE case_id = ANY(%(ids)s) ORDER BY decision_id",
    "copilot_messages": "SELECT * FROM copilot_messages WHERE case_id = ANY(%(ids)s) ORDER BY id",
    "sar_drafts": "SELECT * FROM sar_drafts WHERE case_id = ANY(%(ids)s) ORDER BY id",
    "audit_log": "SELECT * FROM audit_log WHERE case_id = ANY(%(ids)s) ORDER BY case_id, seq",
    "checkpoints": "SELECT * FROM checkpoints WHERE thread_id = ANY(%(ids)s)",
    "checkpoint_blobs": "SELECT * FROM checkpoint_blobs WHERE thread_id = ANY(%(ids)s)",
    "checkpoint_writes": "SELECT * FROM checkpoint_writes WHERE thread_id = ANY(%(ids)s)",
    "guidance.passages": "SELECT id, doc_id, title, publisher, url, jurisdiction, page, section, "
    "text, embedding FROM guidance.passages ORDER BY id",
}


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=lambda d, names: [n for n in names if n in SKIP])


def export_database(conn: psycopg.Connection, case_ids: list[str], seed: Path) -> dict:
    seed.mkdir(parents=True)
    counts = {}
    for table, query in EXPORTS.items():
        sql = psycopg.ClientCursor(conn).mogrify(query, {"ids": case_ids})
        with (
            (seed / f"{table}.csv").open("wb") as f,
            conn.cursor().copy(f"COPY ({sql}) TO STDOUT WITH (FORMAT csv, HEADER true)") as copy,
        ):
            for block in copy:
                f.write(block)
        counts[table] = sum(1 for _ in (seed / f"{table}.csv").open(encoding="utf-8")) - 1
    return counts


def demo_accounts(conn: psycopg.Connection, case_ids: list[str]) -> set[tuple[int, str]]:
    """Every account a demo case shows: subject, case-file accounts, flagged payments."""
    accounts: set[tuple[int, str]] = set()
    rows = conn.execute(
        "SELECT alert, analysis, case_graph FROM cases WHERE case_id = ANY(%s)", [case_ids]
    ).fetchall()
    for alert, analysis, graph in rows:
        accounts.add((int(alert["seed_bank"]), alert["seed_account"]))
        for bank, acct in ((analysis or {}).get("aliases") or {}).values():
            accounts.add((int(bank), acct))
        for node in (graph or {}).get("nodes", []):
            accounts.add((int(node["bank_id"]), node["account"]))
        for t in (analysis or {}).get("triggers") or []:
            accounts.add((int(t["from_bank"]), t["from_account"]))
            accounts.add((int(t["to_bank"]), t["to_account"]))
    return accounts


def export_slice(accounts: set[tuple[int, str]], parquet: Path) -> int:
    parquet.mkdir(parents=True)
    con = duckdb.connect(str(parquet / "tools.duckdb"))
    con.execute(f"ATTACH '{tool_db_path().as_posix()}' AS src (READ_ONLY)")
    con.execute("CREATE TEMP TABLE demo_accounts (b INTEGER, a VARCHAR)")
    con.executemany("INSERT INTO demo_accounts VALUES (?, ?)", sorted(accounts))
    con.execute(
        """
        CREATE TABLE transactions AS
        SELECT t.* FROM src.transactions t
        WHERE (t.from_bank, t.from_account) IN (SELECT b, a FROM demo_accounts)
           OR (t.to_bank, t.to_account) IN (SELECT b, a FROM demo_accounts)
        ORDER BY t.tx_id
        """
    )
    con.execute("CREATE TABLE banks AS SELECT * FROM src.banks")
    n = con.execute("SELECT count(*) FROM transactions").fetchone()[0]
    # The citation verifier reads a Parquet copy of the same rows (still no labels).
    con.execute(
        f"COPY transactions TO '{(parquet / 'transactions.parquet').as_posix()}' (FORMAT parquet)"
    )
    con.close()
    return n


SPACE_README = """---
title: AML Investigation Agent
emoji: 🔎
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: other
short_description: AI-assisted AML case manager on synthetic data
---

# AML Investigation Agent (public demo)

An AI-assisted anti-money-laundering case manager. Transaction monitoring raises alerts,
an AI agent investigates them and recommends an action, and analysts decide under a
four-eyes rule. Code, results and design notes: https://github.com/sehaj-deep/aml-investigation-agent

**Sandbox.** Synthetic data only (IBM AMLworld); nothing is filed with any authority.

- The cases in this demo were reviewed by the AI in advance. Live AI actions (copilot
  questions, SAR drafts, re-investigation) have small daily limits.
- Use the role switch at the top right (Analyst, Supervisor) to try the four-eyes flow.
  There is no login; every restart resets the demo to its reviewed state.

## Data

This Space contains a small slice of the IBM Transactions for Anti-Money Laundering
(AML) dataset, HI-Small (the transactions around the demo cases, without laundering
labels). The dataset is published under the Community Data License Agreement, Sharing,
Version 1.0; see `LICENSE-DATA.md`. Guidance passages are US government publications in
the public domain.
"""

LICENSE_DATA = """# Data licence

The files under `data/parquet/` and the transaction rows under `data/seed/` are a subset
of "IBM Transactions for Anti-Money Laundering (AML)", HI-Small, by E. Altman,
J. Blanusa, L. von Niederhausern, B. Egressy, A. Anghel and K. Atasu (IBM Research),
described in "Realistic Synthetic Financial Transactions for Anti-Money Laundering
Models", NeurIPS 2023 (https://arxiv.org/abs/2306.16424).

The data is made available under the Community Data License Agreement, Sharing,
Version 1.0 (CDLA-Sharing 1.0): https://cdla.dev/sharing-1-0/
This subset is shared under the same agreement. Changes: rows were selected around the
demo cases, and the laundering labels were removed.

The guidance passages under `data/seed/guidance.passages.csv` come from FinCEN and FFIEC
publications, which are works of the US federal government and in the public domain.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload", action="store_true", help="create or update the Space")
    args = parser.parse_args()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    with psycopg.connect(store.database_url()) as conn:
        case_ids = [
            r[0]
            for r in conn.execute(
                "SELECT case_id FROM cases WHERE status IN ('pending_review', 'pending_approval', "
                "'closed', 'escalated') ORDER BY created_at"
            ).fetchall()
        ]
        counts = export_database(conn, case_ids, OUT / "data" / "seed")
        accounts = demo_accounts(conn, case_ids)
    rows = export_slice(accounts, OUT / "data" / "parquet")
    (OUT / "data" / "alert_queue").mkdir()

    copy_tree(ROOT / "aml_agent", OUT / "aml_agent")
    copy_tree(ROOT / "ui", OUT / "ui")
    shutil.copy(ROOT / "requirements.txt", OUT / "requirements.txt")
    (OUT / "space").mkdir()
    for name in ("start.sh", "nginx.conf", "seed.py"):
        shutil.copy(ROOT / "deploy" / "space" / name, OUT / "space" / name)
    shutil.copy(ROOT / "deploy" / "space" / "Dockerfile", OUT / "Dockerfile")
    (OUT / "README.md").write_text(SPACE_README, encoding="utf-8", newline="\n")
    (OUT / "LICENSE-DATA.md").write_text(LICENSE_DATA, encoding="utf-8", newline="\n")

    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1e6
    print(
        json.dumps(
            {
                "cases": len(case_ids),
                "rows": counts,
                "accounts": len(accounts),
                "transactions_in_slice": rows,
                "build_mb": round(size, 1),
            },
            indent=1,
        )
    )
    if args.upload:
        subprocess.run(
            [
                str(HF),
                "repos",
                "create",
                SPACE_ID,
                "--type",
                "space",
                "--space-sdk",
                "docker",
                "--public",
                "--exist-ok",
            ],
            check=True,
        )
        subprocess.run(
            [
                str(HF),
                "upload",
                SPACE_ID,
                str(OUT),
                ".",
                "--repo-type",
                "space",
                "--commit-message",
                "Update the demo",
            ],
            check=True,
        )
        print(f"uploaded: https://huggingface.co/spaces/{SPACE_ID}")


if __name__ == "__main__":
    main()
