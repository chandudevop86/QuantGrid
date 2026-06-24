from __future__ import annotations

import logging
from typing import Any

from Backend.application.monitoring import observe_strategy_execution
from Backend.application.trade_qualification_engine import TradeQualificationEngine
from Backend.domain.engine.trading_engine import TradingEngine
from Backend.domain.models.context import StrategyContext
from Backend.domain.models.order import Order
from Backend.domain.models.signal import StrategySignal


class TradingService:
    def __init__(self, trading_engine: TradingEngine | None = None, tqe: TradeQualificationEngine | None = None) -> None:
        self.trading_engine = trading_engine or TradingEngine()
        self.tqe = tqe or TradeQualificationEngine()
        self.logger = logging.getLogger("quantgrid.strategy")

    def run_strategy(
        self,
        *,
        strategy_name: str,
        data: Any,
        symbol: str,
        capital: float,
        risk_pct: float,
        rr_ratio: float = 2.0,
        params: dict[str, Any] | None = None,
    ) -> list[StrategySignal]:
        context = StrategyContext(symbol=symbol, capital=capital, risk_pct=risk_pct, rr_ratio=rr_ratio, params=params or {})
        try:
            signals = self.trading_engine.scan(strategy_name, data, context)
        except Exception as exc:
            observe_strategy_execution(strategy_name, "failed", error_type=exc.__class__.__name__)
            self.logger.exception(
                "strategy_execution_failed",
                extra={"strategy": strategy_name, "symbol": symbol, "error_type": exc.__class__.__name__},
            )
            raise
        observe_strategy_execution(strategy_name, "success", signal_count=len(signals))
        if self._uses_tqe(strategy_name):
            return [
                self.tqe.annotate_signal(
                    signal,
                    candles=data,
                    capital=capital,
                    risk_pct=risk_pct,
                    h4_candles=context.params.get("h4_candles") or context.params.get("daily_candles"),
                    h1_candles=context.params.get("h1_candles") or context.params.get("htf_candles"),
                    m15_candles=context.params.get("m15_candles") or context.params.get("mtf_candles"),
                )
                for signal in signals
            ]
        return signals

    def create_orders_from_strategy(
        self,
        *,
        strategy_name: str,
        data: Any,
        symbol: str,
        capital: float,
        risk_pct: float,
        rr_ratio: float = 2.0,
        params: dict[str, Any] | None = None,
    ) -> list[Order]:
        signals = self.run_strategy(
            strategy_name=strategy_name,
            data=data,
            symbol=symbol,
            capital=capital,
            risk_pct=risk_pct,
            rr_ratio=rr_ratio,
            params=params,
        )
        return self.trading_engine.create_orders(signals)

    @staticmethod
    def _uses_tqe(strategy_name: str) -> bool:
        return str(strategy_name or "").strip().lower().replace("-", "_").replace(" ", "_") in {
            "amd",
            "breakout",
            "supply_demand",
            "mtf",
            "mtfa",
            "cbt",
            "crt_tbs",
        }
