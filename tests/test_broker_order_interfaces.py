from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from Backend.domain.engine.execution_engine import ExecutionEngine
from Backend.domain.models.order import Order
from Backend.domain.models.signal import StrategySignal
from Backend.domain.shared import IBrokerAdapter, IOrderManager
from Backend.infrastructure.broker.broker_client import PaperBrokerClient


def _signal() -> StrategySignal:
    return StrategySignal(
        strategy_name="mock",
        symbol="NIFTY",
        side="BUY",
        entry_price=100.0,
        stop_loss=95.0,
        target_price=110.0,
        signal_time=datetime(2026, 7, 3, 9, 30, tzinfo=timezone.utc),
        metadata={"quantity": 2},
    )


class MockBroker:
    def __init__(self) -> None:
        self.orders: list[Order] = []

    async def place_order(self, order: Order):
        self.orders.append(order)
        return {"broker_order_id": "mock-1", "status": "confirmed", "symbol": order.symbol}

    def status(self) -> dict:
        return {"provider": "mock", "connected": True}


def test_execution_engine_is_order_manager_contract():
    engine = ExecutionEngine()
    order = engine.order_from_signal(_signal())

    assert isinstance(engine, IOrderManager)
    assert order.symbol == "NIFTY"
    assert order.quantity == 2
    assert order.stop_loss == 95.0
    assert order.target_price == 110.0


def test_mock_broker_implements_broker_adapter_contract():
    broker = MockBroker()
    order = ExecutionEngine().order_from_signal(_signal())
    result = asyncio.run(broker.place_order(order))

    assert isinstance(broker, IBrokerAdapter)
    assert result["status"] == "confirmed"
    assert broker.status()["connected"] is True
    assert broker.orders[0].symbol == "NIFTY"


def test_paper_broker_stays_behind_broker_adapter_contract():
    broker = PaperBrokerClient()
    order = ExecutionEngine().order_from_signal(_signal())
    result = asyncio.run(broker.place_order(order))

    assert isinstance(broker, IBrokerAdapter)
    assert result.confirmed is True
    assert broker.status()["provider"] == "paper"
