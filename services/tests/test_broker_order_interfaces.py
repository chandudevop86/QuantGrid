from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
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

    async def authenticate(self):
        return {"authenticated": True}

    async def get_margin(self):
        return {"available": 100000}

    async def place_order(self, order: Order):
        self.orders.append(order)
        return {"broker_order_id": "mock-1", "status": "confirmed", "symbol": order.symbol}

    async def modify_order(self, broker_order_id: str, updates: dict):
        return {"broker_order_id": broker_order_id, "status": "modified", "updates": updates}

    async def cancel_order(self, broker_order_id: str):
        return {"broker_order_id": broker_order_id, "status": "cancelled"}

    async def get_order_status(self, broker_order_id: str):
        return {"broker_order_id": broker_order_id, "status": "confirmed"}

    async def get_positions(self):
        return []

    async def get_order_book(self):
        return [{"symbol": order.symbol, "quantity": order.quantity} for order in self.orders]

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
    order_book = asyncio.run(broker.get_order_book())

    assert isinstance(broker, IBrokerAdapter)
    assert result["status"] == "confirmed"
    assert broker.status()["connected"] is True
    assert broker.orders[0].symbol == "NIFTY"
    assert order_book[0]["symbol"] == "NIFTY"


def test_paper_broker_stays_behind_broker_adapter_contract():
    broker = PaperBrokerClient()
    order = ExecutionEngine().order_from_signal(_signal())
    result = asyncio.run(broker.place_order(order))
    margin = asyncio.run(broker.get_margin())

    assert isinstance(broker, IBrokerAdapter)
    assert result.confirmed is True
    assert broker.status()["provider"] == "paper"
    assert margin["provider"] == "paper"



def test_dhan_capabilities_fail_closed_without_broker_native_stop(monkeypatch):
    from Backend.infrastructure.broker import dhan_order_adapter
    from Backend.infrastructure.broker.broker_client import broker_capabilities

    monkeypatch.setattr(
        dhan_order_adapter,
        "dhan_credentials",
        lambda: {"client_id": "test-client", "access_token": "test-token"},
    )
    client = dhan_order_adapter.DhanBrokerClient()
    capabilities = broker_capabilities(client)

    assert capabilities.place_order is True
    assert capabilities.order_status is True
    assert capabilities.order_book is True
    assert capabilities.positions is True
    assert capabilities.modify_order is True
    assert capabilities.cancel_order is True
    assert capabilities.correlation_lookup is True
    assert capabilities.partial_fills is True
    assert capabilities.reconciliation_ready is True
    assert capabilities.broker_native_protective_stop is False
    assert capabilities.live_execution_ready is False


def test_paper_capabilities_do_not_claim_live_execution_readiness():
    from Backend.infrastructure.broker.broker_client import PaperBrokerClient, broker_capabilities

    capabilities = broker_capabilities(PaperBrokerClient())

    assert capabilities.provider == "paper"
    assert capabilities.place_order is True
    assert capabilities.live_execution_ready is False
