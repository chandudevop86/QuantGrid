from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from Backend.domain.models.trade_state import TradeState
from Backend.domain.models.execution_mode import ExecutionMode


@dataclass(slots=True)
class Trade:
    trade_id: str = field(default_factory=lambda: str(uuid4()))

    symbol: str = ""

    strategy: str | None = None

    execution_mode: ExecutionMode = ExecutionMode.PAPER

    order_id: str | None = None

    broker_order_id: str | None = None

    position_id: str | None = None

    state: TradeState = TradeState.SIGNAL_GENERATED

    entry_price: float | None = None

    exit_price: float | None = None

    quantity: int = 0

    pnl: float = 0.0

    opened_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    closed_at: datetime | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None