from __future__ import annotations

from typing import Any

from app.domain.engine.trading_engine import TradingEngine
from app.domain.models.context import StrategyContext
from app.domain.models.order import Order
from app.domain.models.signal import StrategySignal


class TradingService:
    def __init__(self, trading_engine: TradingEngine | None = None) -> None:
        self.trading_engine = trading_engine or TradingEngine()

    def run_strategy(self, *, strategy_name: str, data: Any, symbol: str, capital: float, risk_pct: float, rr_ratio: float = 2.0) -> list[StrategySignal]:
        context = StrategyContext(symbol=symbol, capital=capital, risk_pct=risk_pct, rr_ratio=rr_ratio)
        return self.trading_engine.scan(strategy_name, data, context)

    def create_orders_from_strategy(self, *, strategy_name: str, data: Any, symbol: str, capital: float, risk_pct: float, rr_ratio: float = 2.0) -> list[Order]:
        signals = self.run_strategy(strategy_name=strategy_name, data=data, symbol=symbol, capital=capital, risk_pct=risk_pct, rr_ratio=rr_ratio)
        return self.trading_engine.create_orders(signals)
