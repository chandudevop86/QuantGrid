from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TradeAudit:
    trade_id: str
    strategy: str
    symbol: str

    validation_score: float = 0.0

    trend: str = "UNKNOWN"

    bos: bool = False
    choch: bool = False

    liquidity_sweep: bool = False
    sweep_quality: float = 0.0

    fvg: bool = False

    supply_zone: bool = False
    demand_zone: bool = False

    risk_reward: float = 0.0

    exit_reason: str = ""

    reasons: list[str] = field(default_factory=list)

    extra: dict[str, Any] = field(default_factory=dict)