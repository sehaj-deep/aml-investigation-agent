"""Alert and ground-truth schemas.

An Alert is what the agent receives: a seed account and a time window, nothing
else (FR-1). Labels live in a separate GroundTruth record the agent never sees.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    alert_id: str
    seed_bank: int
    seed_account: str
    window_start: datetime
    window_end: datetime

    @model_validator(mode="after")
    def _window_order(self) -> Alert:
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        return self


class GroundTruth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    alert_id: str
    label: Literal["positive", "benign"]
    block_id: int | None = None
    pattern_type: str | None = None
    # For a benign control: the positive alert whose activity and window it matches.
    matched_to: str | None = None
    # True if the source block (or matched block) has rows after 2022/09/10.
    runs_past_primary_period: bool
