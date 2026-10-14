"""Citation verification (FR-7): every cited transaction must exist and match the data.

This is ordinary code with its own read-only data path (the Parquet source of
truth), separate from the agent's MCP tools. It checks:

- every tx_id the model cited exists in the data (an invented ID is a failure even
  though it never becomes an evidence row);
- every evidence row matches the data on parties (bank and account, both sides),
  amount, currency and timestamp;
- grounding: whether each cited tx_id was returned by a tool during the case
  (reported separately; the PRD's faithfulness metric is existence plus match).

A case is `faithful` when all cited tx_ids exist and every evidence row matches.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import duckdb

from aml_agent import config

FIELDS = (
    "from_bank",
    "from_account",
    "to_bank",
    "to_account",
    "amount_paid",
    "currency_paid",
    "timestamp",
)


@dataclass
class EvidenceCheck:
    tx_id: Any
    exists: bool
    mismatches: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exists and not self.mismatches


@dataclass
class CaseVerification:
    faithful: bool
    grounded: bool
    cited: int
    evidence_rows: int
    missing_tx_ids: list
    ungrounded_tx_ids: list
    uncited_evidence: list
    duplicate_evidence: list
    failures: list[dict]

    def as_dict(self) -> dict:
        return asdict(self)

    def warnings(self) -> list[str]:
        out = []
        if self.missing_tx_ids:
            out.append(f"VERIFICATION_FAILED: cited tx_ids not in the data: {self.missing_tx_ids}")
        for f in self.failures:
            if f["exists"]:
                fields = ", ".join(sorted(f["mismatches"]))
                out.append(f"VERIFICATION_FAILED: tx {f['tx_id']} does not match data on {fields}")
        if self.uncited_evidence:
            out.append(f"VERIFICATION_FAILED: evidence rows not cited: {self.uncited_evidence}")
        if self.duplicate_evidence:
            out.append(f"VERIFICATION_FAILED: duplicate evidence rows: {self.duplicate_evidence}")
        if self.ungrounded_tx_ids:
            out.append(f"UNGROUNDED: cited tx_ids no tool returned: {self.ungrounded_tx_ids}")
        return out


def _norm_amount(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)).quantize(Decimal("0.000001"))
    except (InvalidOperation, ValueError):
        return None


def _norm_ts(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M")
    try:
        return datetime.fromisoformat(str(value)).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        return None


class CitationVerifier:
    """Checks case evidence against a `transactions` relation (Parquet by default)."""

    def __init__(self, con: duckdb.DuckDBPyConnection | None = None):
        if con is None:
            con = duckdb.connect()
            path = config.table_path("transactions")
            if not Path(path).exists():
                raise FileNotFoundError(path)
            con.execute(f"CREATE VIEW transactions AS SELECT * FROM '{path.as_posix()}'")
        self.con = con

    def _lookup(self, tx_ids: list[int]) -> dict[int, dict]:
        ids = [t for t in tx_ids if isinstance(t, int) and not isinstance(t, bool)]
        if not ids:
            return {}
        rows = self.con.execute(
            """
            SELECT tx_id, from_bank, from_account, to_bank, to_account,
                   amount_paid, currency_paid, ts
            FROM transactions WHERE tx_id IN (SELECT unnest(?))
            """,
            [ids],
        ).fetchall()
        return {
            r[0]: {
                "from_bank": str(r[1]),
                "from_account": r[2],
                "to_bank": str(r[3]),
                "to_account": r[4],
                "amount_paid": _norm_amount(r[5]),
                "currency_paid": r[6],
                "timestamp": _norm_ts(r[7]),
            }
            for r in rows
        }

    def check_evidence(self, evidence: list[dict]) -> list[EvidenceCheck]:
        data = self._lookup([e.get("tx_id") for e in evidence])
        checks = []
        for e in evidence:
            row = data.get(e.get("tx_id"))
            if row is None:
                checks.append(EvidenceCheck(e.get("tx_id"), exists=False))
                continue
            claimed = {
                "from_bank": str(e.get("from_bank")),
                "from_account": e.get("from_account"),
                "to_bank": str(e.get("to_bank")),
                "to_account": e.get("to_account"),
                "amount_paid": _norm_amount(e.get("amount_paid")),
                "currency_paid": e.get("currency_paid"),
                "timestamp": _norm_ts(e.get("timestamp")),
            }
            mismatches = {
                f: {"case": str(claimed[f]), "data": str(row[f])}
                for f in FIELDS
                if claimed[f] is None or claimed[f] != row[f]
            }
            checks.append(EvidenceCheck(e["tx_id"], exists=True, mismatches=mismatches))
        return checks

    def verify_case(
        self,
        case: dict,
        cited_tx_ids: list[int] | None = None,
        seen_tx_ids: list[int] | None = None,
    ) -> CaseVerification:
        evidence = case.get("evidence", [])
        evidence_ids = [e.get("tx_id") for e in evidence]
        cited = list(dict.fromkeys(cited_tx_ids if cited_tx_ids is not None else evidence_ids))
        existing = self._lookup(cited)
        missing = [t for t in cited if t not in existing]
        checks = self.check_evidence(evidence)
        failures = [
            {"tx_id": c.tx_id, "exists": c.exists, "mismatches": c.mismatches}
            for c in checks
            if not c.ok
        ]
        uncited = [t for t in evidence_ids if t not in cited]
        duplicates = sorted({t for t in evidence_ids if evidence_ids.count(t) > 1})
        ungrounded = [] if seen_tx_ids is None else [t for t in cited if t not in set(seen_tx_ids)]
        faithful = not missing and not failures and not uncited and not duplicates
        return CaseVerification(
            faithful=faithful,
            grounded=not ungrounded,
            cited=len(cited),
            evidence_rows=len(evidence),
            missing_tx_ids=missing,
            ungrounded_tx_ids=ungrounded,
            uncited_evidence=uncited,
            duplicate_evidence=duplicates,
            failures=failures,
        )
