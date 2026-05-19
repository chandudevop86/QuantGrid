from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Side = Literal["BUY", "SELL"]


@dataclass(slots=True)
class BreakoutRange:
    high: float
    low: float
    start_index: int
    end_index: int
    size: float
    atr: float


@dataclass(slots=True)
class BreakoutSetup:
    side: Side
    breakout_range: BreakoutRange
    close: float
    breakout_distance: float
    candle_range_atr: float
    reason: str


@dataclass(slots=True)
class BreakoutScore:
    trend_alignment: int = 0
    breakout_strength: int = 0
    momentum_confirmation: int = 0
    distance_from_vwap: int = 0
    volatility_expansion: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.trend_alignment
            + self.breakout_strength
            + self.momentum_confirmation
            + self.distance_from_vwap
            + self.volatility_expansion
        )

    def to_dict(self) -> dict[str, int | list[str]]:
        return {
            "trend_alignment": self.trend_alignment,
            "breakout_strength": self.breakout_strength,
            "momentum_confirmation": self.momentum_confirmation,
            "distance_from_vwap": self.distance_from_vwap,
            "volatility_expansion": self.volatility_expansion,
            "total": self.total,
            "reasons": self.reasons,
        }
