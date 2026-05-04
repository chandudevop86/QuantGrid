from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Order:
    symbol: str
    side: str
    quantity: int
    order_type: str = "MARKET"
    price: float | None = None
    stop_loss: float | None = None
    target_price: float | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
