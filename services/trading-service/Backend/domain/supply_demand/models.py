from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Side = Literal["BUY", "SELL"]
ZoneType = Literal["demand", "supply"]
Bias = Literal["bullish", "bearish", "neutral"]


@dataclass(slots=True)
class SDZone:
    zone_type: ZoneType
    low: float
    high: float
    base_start: int
    base_end: int
    impulse_index: int
    impulse_strength: float
    touches: int = 0

    @property
    def side(self) -> Side:
        return "BUY" if self.zone_type == "demand" else "SELL"

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0

    @property
    def width(self) -> float:
        return max(0.0, self.high - self.low)


@dataclass(slots=True)
class HTFBias:
    bias: Bias
    trend_strength: float
    reason: str

    def aligns(self, side: Side) -> bool:
        return (side == "BUY" and self.bias == "bullish") or (side == "SELL" and self.bias == "bearish")


@dataclass(slots=True)
class LiquidityEvent:
    side: Side
    swept_level: float
    index: int
    quality: float
    reason: str


@dataclass(slots=True)
class EntryConfirmation:
    kind: Literal["rejection", "engulfing"]
    strength: float
    reason: str


@dataclass(slots=True)
class SDScore:
    zone_freshness: int = 0
    htf_alignment: int = 0
    entry_confirmation: int = 0
    liquidity_sweep: int = 0
    momentum_confirmation: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.zone_freshness
            + self.htf_alignment
            + self.entry_confirmation
            + self.liquidity_sweep
            + self.momentum_confirmation
        )

    def to_dict(self) -> dict[str, int | list[str]]:
        return {
            "zone_freshness": self.zone_freshness,
            "htf_alignment": self.htf_alignment,
            "entry_confirmation": self.entry_confirmation,
            "liquidity_sweep": self.liquidity_sweep,
            "momentum_confirmation": self.momentum_confirmation,
            "total": self.total,
            "reasons": self.reasons,
        }
