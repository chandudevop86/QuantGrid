from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from Backend.application.trading_service import TradingService
from Backend.trading_system.execution import ExecutionEngine, ExecutionRequest, ExecutionResult


@dataclass(slots=True)
class SignalProducer:
    service: TradingService
    queue: asyncio.Queue[ExecutionRequest]

    async def publish_from_candles(
        self,
        *,
        strategy_name: str,
        candles: list[dict[str, Any]],
        symbol: str,
        capital: float,
        risk_pct: float,
        rr_ratio: float = 2.0,
    ) -> int:
        signals = self.service.run_strategy(
            strategy_name=strategy_name,
            data=candles,
            symbol=symbol,
            capital=capital,
            risk_pct=risk_pct,
            rr_ratio=rr_ratio,
        )
        for signal in signals:
            await self.queue.put(ExecutionRequest(signal=signal, market_price=signal.entry_price))
        return len(signals)


@dataclass(slots=True)
class ExecutionConsumer:
    engine: ExecutionEngine
    queue: asyncio.Queue[ExecutionRequest]

    async def run_once(self) -> ExecutionResult:
        request = await self.queue.get()
        try:
            return await self.engine.execute_signal(request.signal, market_price=request.market_price)
        finally:
            self.queue.task_done()
