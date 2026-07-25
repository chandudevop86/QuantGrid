from __future__ import annotations

from datetime import datetime, timezone

from Backend.domain.models.order import Order
from Backend.domain.models.signal import StrategySignal
from Backend.domain.shared import IOrderManager


class ExecutionEngine(IOrderManager):
    """Convert a validated strategy signal into the canonical order model."""

    def order_from_signal(self, signal: StrategySignal, *, quantity: int | None = None) -> Order:
        resolved_quantity = quantity if quantity is not None else signal.metadata.get("quantity", 1)
        return Order(
            symbol=signal.symbol,
            side=signal.side,
            quantity=int(resolved_quantity),
            price=signal.entry_price,
            stop_loss=signal.stop_loss,
            target_price=signal.target_price,
            trailing_stop_loss=signal.trailing_stop_loss,
            trailing_stop_pct=signal.trailing_stop_pct,
            created_at=datetime.now(timezone.utc),
            metadata={
                "strategy_name": signal.strategy_name,
                "source": "signal_based",
                "trailing_stop_loss": signal.trailing_stop_loss,
                "trailing_stop_pct": signal.trailing_stop_pct,
            },
        )
