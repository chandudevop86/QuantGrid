from __future__ import annotations

from datetime import datetime

from Backend.domain.models.order import Order
from Backend.domain.models.signal import StrategySignal


class ExecutionEngine:
    def order_from_signal(self, signal: StrategySignal, *, quantity: int | None = None) -> Order:
        return Order(
            symbol=signal.symbol, 
            side=signal.side, 
            quantity=int(quantity if quantity is not None else signal.metadata.get("quantity", 1)), 
            price=signal.entry_price, 
            stop_loss=signal.stop_loss,
            target_price=signal.target_price, 
            trailing_stop_loss=signal.trailing_stop_loss,
            trailing_stop_pct=signal.trailing_stop_pct,
            created_at=datetime.utcnow(),
            metadata={
                "strategy_name": signal.strategy_name,
                "source": "signal_based",
                "trailing_stop_loss": signal.trailing_stop_loss,
                "trailing_stop_pct": signal.trailing_stop_pct,
            }
       )
from fastapi import APIRouter

router = APIRouter()

