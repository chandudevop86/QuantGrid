from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from Backend.domain.models.execution_mode import ExecutionMode
from Backend.domain.models.order_side import OrderSide
from Backend.domain.models.order_status import OrderStatus
from Backend.domain.models.order_type import OrderType


@dataclass(slots=True)
class Order:
    order_id: str = field(default_factory=lambda: str(uuid4()))

    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: int = 0

    order_type: OrderType = OrderType.MARKET

    price: float | None = None

    stop_loss: float | None = None
    target_price: float | None = None

    trailing_stop_loss: float | None = None
    trailing_stop_pct: float | None = None

    broker_order_id: str | None = None

    status: OrderStatus = OrderStatus.CREATED

    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    submitted_at: datetime | None = None
    filled_at: datetime | None = None

    average_fill_price: float | None = None
    filled_quantity: int = 0

    strategy: str | None = None

    execution_mode: ExecutionMode = ExecutionMode.PAPER

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status in {
            OrderStatus.CREATED,
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
        }

    @property
    def is_completed(self) -> bool:
        return self.status in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }

    @property
    def remaining_quantity(self) -> int:
        return max(0, self.quantity - self.filled_quantity)

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED