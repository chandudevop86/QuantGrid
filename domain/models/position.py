from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Position:
    symbol: str
    side: str
    quantity: int
    entry_price: float
    stop_loss: float | None = None
    target_price: float | None = None
    opened_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def unrealized_pnl(self, last_price: float) -> float:
        multiplier = 1.0 if self.side.upper() == "BUY" else -1.0
        return (float(last_price) - float(self.entry_price)) * multiplier * int(self.quantity)
