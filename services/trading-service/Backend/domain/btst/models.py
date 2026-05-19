from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Side = Literal["BUY", "SELL"]
Trend = Literal["bullish", "bearish", "sideways"]


@dataclass(slots=True)
class SwingStructure:
    trend: Trend
    side: Side | None
    previous_swing_high: float | None
    previous_swing_low: float | None
    breakout_confirmed: bool
    structure_confirmed: bool
    reason: str


@dataclass(slots=True)
class EODConfirmation:
    side: Side
    near_close: bool
    close_strength: float
    day_high: float
    day_low: float
    reason: str


@dataclass(slots=True)
class GapAssessment:
    allowed: bool
    probability_score: float
    reason: str


@dataclass(slots=True)
class BTSTScore:
    trend_alignment: int = 0
    structure_breakout: int = 0
    eod_strength: int = 0
    momentum_confirmation: int = 0
    vwap_alignment: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.trend_alignment
            + self.structure_breakout
            + self.eod_strength
            + self.momentum_confirmation
            + self.vwap_alignment
        )

    def to_dict(self) -> dict[str, int | list[str]]:
        return {
            "trend_alignment": self.trend_alignment,
            "structure_breakout": self.structure_breakout,
            "eod_strength": self.eod_strength,
            "momentum_confirmation": self.momentum_confirmation,
            "vwap_alignment": self.vwap_alignment,
            "total": self.total,
            "reasons": self.reasons,
        }
