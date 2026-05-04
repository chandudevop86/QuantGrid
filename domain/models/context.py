from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StrategyContext:
    symbol: str
    capital: float
    risk_pct: float
    rr_ratio: float = 2.0
    params: dict[str, Any] = field(default_factory=dict)
