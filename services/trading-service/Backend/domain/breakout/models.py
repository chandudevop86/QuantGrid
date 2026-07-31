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
    # Original scoring
    trend_alignment: int = 0          # 0-3
    breakout_strength: int = 0        # 0-3
    momentum_confirmation: int = 0    # 0-2
    distance_from_vwap: int = 0       # 0-1
    volatility_expansion: int = 0     # 0-1

    # New scoring
    volume_confirmation: int = 0      # 0-2
    adx_strength: int = 0             # 0-2
    candle_quality: int = 0           # 0-1

    reasons: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.trend_alignment
            + self.breakout_strength
            + self.momentum_confirmation
            + self.distance_from_vwap
            + self.volatility_expansion
            + self.volume_confirmation
            + self.adx_strength
            + self.candle_quality
        )

    def to_dict(self) -> dict[str, int | list[str]]:
        return {
            "trend_alignment": self.trend_alignment,
            "breakout_strength": self.breakout_strength,
            "momentum_confirmation": self.momentum_confirmation,
            "distance_from_vwap": self.distance_from_vwap,
            "volatility_expansion": self.volatility_expansion,
            "volume_confirmation": self.volume_confirmation,
            "adx_strength": self.adx_strength,
            "candle_quality": self.candle_quality,
            "total": self.total,
            "max_score": 15,
            "reasons": self.reasons,
        }