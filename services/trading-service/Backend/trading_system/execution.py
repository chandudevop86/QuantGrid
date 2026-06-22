from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from Backend.domain.engine.execution_engine import ExecutionEngine as OrderFactory
from Backend.domain.models.signal import StrategySignal
from Backend.trading_system.broker import BrokerInterface, BrokerOrder, MockBroker
from Backend.trading_system.logging import get_logger
from Backend.trading_system.risk import GlobalRiskManager
from Backend.trading_system.slippage import SlippageModel


PriceProvider = Callable[[str], float]


@dataclass(slots=True)
class ExecutionRequest:
    signal: StrategySignal
    market_price: float | None = None
    received_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class ExecutionResult:
    accepted: bool
    status: str
    reason: str
    order: BrokerOrder | None = None
    requested_price: float | None = None
    execution_price: float | None = None
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionEngine:
    def __init__(
        self,
        broker: BrokerInterface | None = None,
        risk_manager: GlobalRiskManager | None = None,
        slippage_model: SlippageModel | None = None,
        *,
        order_execution_delay_ms: int = 0,
        max_slippage_bps: float = 25.0,
        price_provider: PriceProvider | None = None,
    ) -> None:
        self.broker = broker or MockBroker()
        self.risk_manager = risk_manager or GlobalRiskManager()
        self.slippage_model = slippage_model or SlippageModel()
        self.order_execution_delay_ms = max(0, int(order_execution_delay_ms))
        self.max_slippage_bps = float(max_slippage_bps)
        self.price_provider = price_provider
        self.order_factory = OrderFactory()
        self.logger = get_logger(__name__)

    async def execute_signal(self, signal: StrategySignal, *, market_price: float | None = None) -> ExecutionResult:
        started_at = datetime.utcnow()
        risk_decision = self.risk_manager.validate_order(signal, now=started_at)
        if not risk_decision.accepted:
            reason = risk_decision.reason
            self.logger.info("signal_rejected", {"symbol": signal.symbol, "reason": reason, "event": "signal_rejected"})
            return ExecutionResult(False, "rejected", reason)

        if self.order_execution_delay_ms:
            await asyncio.sleep(self.order_execution_delay_ms / 1000.0)

        requested_price = float(signal.entry_price)
        live_price = self._resolve_market_price(signal, market_price)
        slipped_price = self.slippage_model.apply(live_price, signal.side, "entry")
        slippage_bps = abs(slipped_price - requested_price) / max(requested_price, 1e-9) * 10_000.0
        if slippage_bps > self.max_slippage_bps:
            reason = "slippage_threshold_exceeded"
            self.logger.info(
                "order_rejected",
                {"symbol": signal.symbol, "reason": reason, "slippage_bps": slippage_bps, "event": "order_rejected"},
            )
            return ExecutionResult(False, "rejected", reason, requested_price=requested_price, execution_price=slipped_price)

        order = self.order_factory.order_from_signal(signal, quantity=risk_decision.quantity)
        broker_order = await self.broker.place_order(order.symbol, order.side, int(order.quantity), slipped_price)
        latency_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)

        if broker_order.status == "filled":
            self.risk_manager.record_trade_opened(started_at)

        self.logger.info(
            "order_placed",
            {
                "symbol": signal.symbol,
                "side": signal.side,
                "qty": int(order.quantity),
                "status": broker_order.status,
                "order_id": broker_order.order_id,
                "latency_ms": latency_ms,
                "event": "order_placed",
            },
        )
        return ExecutionResult(
            accepted=broker_order.status != "rejected",
            status=broker_order.status,
            reason=broker_order.status,
            order=broker_order,
            requested_price=requested_price,
            execution_price=broker_order.filled_price or slipped_price,
            latency_ms=latency_ms,
            metadata={
                "slippage_bps": slippage_bps,
                "risk_decision": {
                    "quantity": risk_decision.quantity,
                    "risk_amount": risk_decision.risk_amount,
                    "risk_per_unit": risk_decision.risk_per_unit,
                    "risk_pct": risk_decision.risk_pct,
                },
            },
        )

    async def consume(self, queue: asyncio.Queue[ExecutionRequest], *, stop_after: int | None = None) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        while stop_after is None or len(results) < stop_after:
            request = await queue.get()
            try:
                results.append(await self.execute_signal(request.signal, market_price=request.market_price))
            finally:
                queue.task_done()
        return results

    def _resolve_market_price(self, signal: StrategySignal, market_price: float | None) -> float:
        if self.price_provider is not None:
            return float(self.price_provider(signal.symbol))
        return float(market_price if market_price is not None else signal.entry_price)


async def publish_signal(queue: asyncio.Queue[ExecutionRequest], signal: StrategySignal, *, market_price: float | None = None) -> None:
    await queue.put(ExecutionRequest(signal=signal, market_price=market_price))
