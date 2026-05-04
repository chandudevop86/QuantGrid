from __future__ import annotations

from typing import Any

from domain.engine.execution_engine import ExecutionEngine
from domain.engine.strategy_engine import StrategyEngine
from domain.models.context import StrategyContext
from domain.models.order import Order
from domain.models.signal import StrategySignal
from domain.risk.risk_manager import RiskManager


class TradingEngine:
    def __init__(self, strategy_engine: StrategyEngine | None = None, execution_engine: ExecutionEngine | None = None, risk_manager: RiskManager | None = None) -> None:
        self.strategy_engine = strategy_engine or StrategyEngine()
        self.execution_engine = execution_engine or ExecutionEngine()
        self.risk_manager = risk_manager or RiskManager()

    def scan(self, strategy_name: str, data: Any, context: StrategyContext) -> list[StrategySignal]:
        signals = self.strategy_engine.run(strategy_name, data, context)
        return [signal for signal in signals if self.risk_manager.validate_signal(signal)]

    def create_orders(self, signals: list[StrategySignal]) -> list[Order]:
        return [self.execution_engine.order_from_signal(signal) for signal in signals]
