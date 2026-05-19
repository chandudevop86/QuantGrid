from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Side = Literal["BUY", "SELL"]
Bias = Literal["bullish", "bearish", "sideways"]


@dataclass(slots=True)
class HTFTrend:
    bias: Bias
    ema_aligned: bool
    structure_confirmed: bool
    trend_strength: float
    structure_level: float | None
    reason: str

    @property
    def side(self) -> Side | None:
        if self.bias == "bullish":
            return "BUY"
        if self.bias == "bearish":
            return "SELL"
        return None


@dataclass(slots=True)
class PullbackSetup:
    side: Side
    touched_ema21: bool
    touched_vwap: bool
    quality: float
    setup_index: int
    reason: str


@dataclass(slots=True)
class LTFEntry:
    side: Side
    kind: Literal["engulfing", "rejection"]
    rsi_confirmed: bool
    vwap_confirmed: bool
    quality: float
    reason: str


@dataclass(slots=True)
class MTFScore:
    htf_trend_alignment: int = 0
    structure_confirmation: int = 0
    pullback_quality: int = 0
    entry_confirmation: int = 0
    momentum_confirmation: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.htf_trend_alignment
            + self.structure_confirmation
            + self.pullback_quality
            + self.entry_confirmation
            + self.momentum_confirmation
        )

    def to_dict(self) -> dict[str, int | list[str]]:
        return {
            "htf_trend_alignment": self.htf_trend_alignment,
            "structure_confirmation": self.structure_confirmation,
            "pullback_quality": self.pullback_quality,
            "entry_confirmation": self.entry_confirmation,
            "momentum_confirmation": self.momentum_confirmation,
            "total": self.total,
            "reasons": self.reasons,
        }
