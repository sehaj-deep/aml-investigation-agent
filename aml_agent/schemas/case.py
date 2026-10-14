"""Case output (FR-4), the model's structured replies, and human decisions (FR-5)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

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
    rationale: str = Field(min_length=1, max_length=2000)
    key_tx_ids: list[int] = Field(default_factory=list, max_length=MAX_EVIDENCE)


class DraftReply(_Strict):
    summary: str = Field(min_length=1, max_length=4000)
    evidence_tx_ids: list[int] = Field(default_factory=list, max_length=MAX_EVIDENCE)
    recommended_action: Action
    confidence: Confidence
    limitations: str = Field(min_length=1, max_length=2000)


# The case (FR-4). Evidence rows are filled by code from get_transactions.


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


class Decision(_Strict):
    action: Literal["approve", "reject", "request_more"]
    reason: str = Field(min_length=3, max_length=2000)
    reviewer: str = Field(min_length=1, max_length=100)
    decided_at: datetime | None = None
