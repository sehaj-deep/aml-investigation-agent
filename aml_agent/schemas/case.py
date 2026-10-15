"""Case output (FR-4), the model's structured replies, and human decisions (FR-5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PatternType = Literal[
    "fan-out",
    "fan-in",
    "cycle",
    "gather-scatter",
    "scatter-gather",
    "bipartite",
    "stack",
    "random",
    "none",
]
Action = Literal["escalate", "close", "needs_more_info"]
Confidence = Literal["low", "medium", "high"]

MAX_EVIDENCE = 30


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# What the model returns (validated; the model never writes amounts or parties).


class HypothesisReply(_Strict):
    pattern_hypothesis: PatternType
    # Accounts that form the pattern: case-file labels ("A3"), "bank_id/account"
    # strings, or {"bank_id": ..., "account": ...}. Code collects the evidence from them.
    pattern_accounts: list[str | dict[str, Any]] = Field(
        default_factory=list, max_length=MAX_EVIDENCE
    )
    rationale: str = Field(min_length=1, max_length=2000)


class DraftReply(_Strict):
    summary: str = Field(min_length=1, max_length=4000)
    # Evidence is collected by code from the hypothesis accounts; IDs the model may still
    # list here are accepted and ignored.
    evidence_tx_ids: list[int] = Field(default_factory=list, max_length=100)
    recommended_action: Action
    confidence: Confidence
    limitations: str = Field(min_length=1, max_length=2000)


# The case (FR-4). Evidence rows are filled by code from get_transfers_among.


class Evidence(_Strict):
    """FR-4 evidence row. Banks are integer bank IDs as strings; the amount is an exact
    decimal string (not a float) so verification can compare it exactly."""

    tx_id: int
    from_bank: str
    from_account: str
    to_bank: str
    to_account: str
    amount_paid: str
    currency_paid: str
    timestamp: str


class GuidanceCitation(_Strict):
    chunk_id: str
    source: str
    jurisdiction: str
    quote_span: str


class Case(_Strict):
    case_id: str
    pattern_hypothesis: PatternType
    summary: str
    evidence: list[Evidence]
    guidance_citations: list[GuidanceCitation] = Field(default_factory=list)
    recommended_action: Action
    confidence: Confidence
    limitations: str


# Analyst outcomes on a case ready for review, and the supervisor's answer to an
# escalation (four-eyes rule: a second person, with the supervisor role, confirms).
ANALYST_ACTIONS = ("close", "escalate", "request_more")
SUPERVISOR_ACTIONS = ("confirm_escalation", "return_to_analyst")


class Decision(_Strict):
    action: Literal["close", "escalate", "request_more", "confirm_escalation", "return_to_analyst"]
    reason: str = Field(min_length=3, max_length=2000)
    reviewer: str = Field(min_length=1, max_length=100)
    # Self-declared: there is no login (sandbox by design). The rule is enforced on the
    # recorded names and roles and audited; it is a workflow control, not authentication.
    role: Literal["analyst", "supervisor"] = "analyst"
    decided_at: datetime | None = None
