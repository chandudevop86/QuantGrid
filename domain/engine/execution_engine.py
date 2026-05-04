from __future__ import annotations

from datetime import datetime

from app.domain.models.order import Order
from app.domain.models.signal import StrategySignal


class ExecutionEngine:
    def order_from_signal(self, signal: StrategySignal) -> Order:
        return Order(symbol=signal.symbol, side=signal.side, quantity=int(signal.metadata.get("quantity", 1)), price=signal.entry_price, stop_loss=signal.stop_loss, target_price=signal.target_price, created_at=datetime.utcnow(), metadata={"strategy_name": signal.strategy_name})
