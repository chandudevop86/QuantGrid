from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class StrategySignal:
    strategy_name: str
    symbol: str
    side: str
    entry_price: float
    stop_loss: float
    target_price: float
    signal_time: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def risk_per_unit(self) -> float:
        return abs(float(self.entry_price) - float(self.stop_loss))

    @property
    def reward_per_unit(self) -> float:
        return abs(float(self.target_price) - float(self.entry_price))
