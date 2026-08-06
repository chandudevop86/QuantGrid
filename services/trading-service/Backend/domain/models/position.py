from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from Backend.domain.models.position_status import PositionStatus


@dataclass(slots=True)
class Position:
    symbol: str
    side: str
    quantity: int
    entry_price: float

    position_id: str = field(default_factory=lambda: str(uuid4()))

    current_price: float | None = None
    exit_price: float | None = None

    stop_loss: float | None = None
    target_price: float | None = None

    status: PositionStatus = PositionStatus.OPEN

    opened_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    closed_at: datetime | None = None

    strategy: str | None = None
    execution_mode: str | None = None
    broker_order_id: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.status == PositionStatus.OPEN

    def unrealized_pnl(self, last_price: float) -> float:
        multiplier = 1 if self.side.upper() == "BUY" else -1
        return (last_price - self.entry_price) * multiplier * self.quantity

    def realized_pnl(self) -> float:
        if self.exit_price is None:
            return 0.0

        multiplier = 1 if self.side.upper() == "BUY" else -1
        return (self.exit_price - self.entry_price) * multiplier * self.quantity