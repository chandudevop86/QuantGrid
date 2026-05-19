from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


Side = Literal["BUY", "SELL"]
ZoneType = Literal["supply", "demand"]
PhaseName = Literal["accumulation", "manipulation", "distribution"]


@dataclass(slots=True)
class LiquidityRange:
    high: float
    low: float
    start_index: int
    end_index: int
    equal_highs: int
    equal_lows: int
    atr: float

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2.0

    @property
    def width(self) -> float:
        return max(0.0, self.high - self.low)


@dataclass(slots=True)
class LiquiditySweep:
    side: Side
    swept_level: float
    sweep_index: int
    wick_extreme: float
    close_price: float
    quality: float
    direction_after_sweep: Side


@dataclass(slots=True)
class FVGZone:
    side: Side
    low: float
    high: float
    created_index: int
    mitigated_index: int | None = None

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0


@dataclass(slots=True)
class SupplyDemandZone:
    zone_type: ZoneType
    low: float
    high: float
    created_index: int
    touches: int = 0

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0


@dataclass(slots=True)
class AMDContext:
    phase: PhaseName
    liquidity_range: LiquidityRange
    sweep: LiquiditySweep
    distribution_index: int
    strength: float


@dataclass(slots=True)
class ScoreBreakdown:
    amd_phase: int = 0
    liquidity_sweep: int = 0
    fvg_validity: int = 0
    zone_confluence: int = 0
    htf_alignment: int = 0
    entry_confirmation: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.amd_phase
            + self.liquidity_sweep
            + self.fvg_validity
            + self.zone_confluence
            + self.htf_alignment
            + self.entry_confirmation
        )

    def to_dict(self) -> dict[str, int | list[str]]:
        return {
            "amd_phase": self.amd_phase,
            "liquidity_sweep": self.liquidity_sweep,
            "fvg_validity": self.fvg_validity,
            "zone_confluence": self.zone_confluence,
            "htf_alignment": self.htf_alignment,
            "entry_confirmation": self.entry_confirmation,
            "total": self.total,
            "reasons": self.reasons,
        }
