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



def test_dhan_capabilities_report_broker_native_super_order_support(monkeypatch):
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
    assert capabilities.protected_order_submission is True
    # Dhan exposes the Super Order API, but QuantGrid has not yet proven the
    # complete protected submission + restart/reconciliation lifecycle.
    assert capabilities.broker_native_protective_stop is False
    assert capabilities.live_execution_ready is False


def test_paper_capabilities_do_not_claim_live_execution_readiness():
    from Backend.infrastructure.broker.broker_client import PaperBrokerClient, broker_capabilities

    capabilities = broker_capabilities(PaperBrokerClient())

    assert capabilities.provider == "paper"
    assert capabilities.place_order is True
    assert capabilities.protected_order_submission is False
    assert capabilities.live_execution_ready is False



def test_dhan_correlation_lookup_uses_authoritative_endpoint(monkeypatch):
    import asyncio
    from Backend.infrastructure.broker import dhan_order_adapter

    monkeypatch.setattr(
        dhan_order_adapter,
        "dhan_credentials",
        lambda: {"client_id": "test-client", "access_token": "test-token"},
    )
    client = dhan_order_adapter.DhanBrokerClient()
    calls = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        return {
            "orderId": "DHAN-123",
            "correlationId": "OMS-abc",
            "orderStatus": "PENDING",
            "transactionType": "BUY",
            "securityId": "12345",
            "quantity": 25,
        }

    monkeypatch.setattr(client, "_request", fake_request)

    result = asyncio.run(client.find_order_by_correlation_id("OMS-abc"))

    assert calls == [("GET", "/orders/external/OMS-abc", None)]
    assert result is not None
    assert result.broker_order_id == "DHAN-123"
    assert result.status == "open"


def test_dhan_correlation_lookup_missing_result_does_not_invent_rejection(monkeypatch):
    import asyncio
    from Backend.infrastructure.broker import dhan_order_adapter

    monkeypatch.setattr(
        dhan_order_adapter,
        "dhan_credentials",
        lambda: {"client_id": "test-client", "access_token": "test-token"},
    )
    client = dhan_order_adapter.DhanBrokerClient()

    def missing_request(method, path, payload=None):
        raise dhan_order_adapter.BrokerAdapterError("order not found")

    monkeypatch.setattr(client, "_request", missing_request)

    assert asyncio.run(client.find_order_by_correlation_id("OMS-missing")) is None



def test_dhan_places_broker_native_protected_super_order(monkeypatch):
    import asyncio
    from Backend.domain.models.order import Order
    from Backend.infrastructure.broker import dhan_order_adapter

    monkeypatch.setattr(
        dhan_order_adapter,
        "dhan_credentials",
        lambda: {"client_id": "test-client", "access_token": "test-token"},
    )
    client = dhan_order_adapter.DhanBrokerClient()
    calls = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        return {"orderId": "SUPER-1", "orderStatus": "PENDING"}

    monkeypatch.setattr(client, "_request", fake_request)
    order = Order(
        symbol="NIFTY",
        side="BUY",
        quantity=25,
        price=100.0,
        stop_loss=95.0,
        target_price=110.0,
        metadata={
            "security_id": "12345",
            "exchange_segment": "NSE_FNO",
            "product_type": "INTRADAY",
            "correlation_id": "OMS-safe-123",
            "trailing_jump": 2.0,
        },
    )

    result = asyncio.run(client.place_protected_order(order))

    assert result.broker_order_id == "SUPER-1"
    assert calls[0][0:2] == ("POST", "/super/orders")
    payload = calls[0][2]
    assert payload["targetPrice"] == 110.0
    assert payload["stopLossPrice"] == 95.0
    assert payload["trailingJump"] == 2.0


def test_dhan_protected_order_rejects_invalid_buy_geometry(monkeypatch):
    import asyncio
    import pytest
    from Backend.domain.models.order import Order
    from Backend.infrastructure.broker import dhan_order_adapter

    monkeypatch.setattr(
        dhan_order_adapter,
        "dhan_credentials",
        lambda: {"client_id": "test-client", "access_token": "test-token"},
    )
    client = dhan_order_adapter.DhanBrokerClient()
    order = Order(
        symbol="NIFTY",
        side="BUY",
        quantity=25,
        price=100.0,
        stop_loss=105.0,
        target_price=110.0,
        metadata={"security_id": "12345", "correlation_id": "OMS-safe-123"},
    )

    with pytest.raises(dhan_order_adapter.BrokerAdapterError, match="protected BUY"):
        asyncio.run(client.place_protected_order(order))


def test_dhan_capabilities_claim_native_protection_only_after_super_order_support(monkeypatch):
    from Backend.infrastructure.broker.broker_client import broker_capabilities
    from Backend.infrastructure.broker import dhan_order_adapter

    monkeypatch.setattr(
        dhan_order_adapter,
        "dhan_credentials",
        lambda: {"client_id": "test-client", "access_token": "test-token"},
    )
    capabilities = broker_capabilities(dhan_order_adapter.DhanBrokerClient())

    assert capabilities.protected_order_submission is True
    assert capabilities.broker_native_protective_stop is False
    assert capabilities.live_execution_ready is False



def test_dhan_partial_fill_keeps_total_filled_and_remaining_quantities_distinct(monkeypatch):
    import asyncio
    from Backend.infrastructure.broker import dhan_order_adapter

    monkeypatch.setattr(
        dhan_order_adapter,
        "dhan_credentials",
        lambda: {"client_id": "test-client", "access_token": "test-token"},
    )
    client = dhan_order_adapter.DhanBrokerClient()

    monkeypatch.setattr(
        client,
        "_request",
        lambda method, path, payload=None: {
            "orderId": "DHAN-PARTIAL-1",
            "orderStatus": "PENDING",
            "tradingSymbol": "NIFTY",
            "transactionType": "BUY",
            "quantity": 25,
            "filledQty": 10,
            "remainingQuantity": 15,
            "averageTradedPrice": 101.25,
        },
    )

    result = asyncio.run(client.get_order_status("DHAN-PARTIAL-1"))

    assert result.status == "partially_filled"
    assert result.quantity == 25
    assert result.filled_quantity == 10
    assert result.remaining_quantity == 15
    assert result.price == 101.25


def test_dhan_quantities_can_authoritatively_promote_stale_status_to_filled(monkeypatch):
    import asyncio
    from Backend.infrastructure.broker import dhan_order_adapter

    monkeypatch.setattr(
        dhan_order_adapter,
        "dhan_credentials",
        lambda: {"client_id": "test-client", "access_token": "test-token"},
    )
    client = dhan_order_adapter.DhanBrokerClient()
    monkeypatch.setattr(
        client,
        "_request",
        lambda method, path, payload=None: {
            "orderId": "DHAN-FILLED-QTY-1",
            "orderStatus": "PENDING",
            "quantity": 25,
            "filledQty": 25,
            "remainingQuantity": 0,
            "averageTradedPrice": 102.0,
        },
    )

    result = asyncio.run(client.get_order_status("DHAN-FILLED-QTY-1"))

    assert result.status == "filled"
    assert result.filled_quantity == 25
    assert result.remaining_quantity == 0



def test_dhan_super_order_status_reports_active_stop_protection(monkeypatch):
    import asyncio
    from Backend.infrastructure.broker import dhan_order_adapter

    monkeypatch.setattr(dhan_order_adapter, "dhan_credentials", lambda: {"client_id": "x", "access_token": "y"})
    client = dhan_order_adapter.DhanBrokerClient()
    monkeypatch.setattr(client, "get_super_orders", lambda: None)

    async def fake_orders():
        return [{
            "orderId": "SUPER-PROTECTED-1", "orderStatus": "PART_TRADED",
            "quantity": 25, "filledQty": 10, "remainingQuantity": 15,
            "legName": "ENTRY_LEG",
            "legDetails": [
                {"orderId": "SL-1", "legName": "STOP_LOSS_LEG", "orderStatus": "PENDING",
                 "totalQuatity": 10, "remainingQuantity": 10, "triggeredQuantity": 10, "price": 95},
                {"orderId": "TG-1", "legName": "TARGET_LEG", "orderStatus": "PENDING",
                 "totalQuatity": 10, "remainingQuantity": 10, "triggeredQuantity": 10, "price": 110},
            ],
        }]
    monkeypatch.setattr(client, "get_super_orders", fake_orders)

    result = asyncio.run(client.get_super_order_status("SUPER-PROTECTED-1"))
    assert result is not None
    assert result.status == "partially_filled"
    protection = result.metadata["super_order"]["protection"]
    assert protection["exposed_quantity"] == 10
    assert protection["stop_loss_active"] is True
    assert protection["protected"] is True


def test_dhan_super_order_filled_exposure_without_stop_is_unprotected(monkeypatch):
    import asyncio
    from Backend.infrastructure.broker import dhan_order_adapter

    monkeypatch.setattr(dhan_order_adapter, "dhan_credentials", lambda: {"client_id": "x", "access_token": "y"})
    client = dhan_order_adapter.DhanBrokerClient()

    async def fake_orders():
        return [{
            "orderId": "SUPER-NO-STOP-1", "orderStatus": "TRADED",
            "quantity": 25, "filledQty": 25, "remainingQuantity": 0,
            "legName": "ENTRY_LEG", "legDetails": [
                {"orderId": "TG-2", "legName": "TARGET_LEG", "orderStatus": "PENDING",
                 "totalQuatity": 25, "triggeredQuantity": 25, "price": 110},
            ],
        }]
    monkeypatch.setattr(client, "get_super_orders", fake_orders)

    result = asyncio.run(client.get_super_order_status("SUPER-NO-STOP-1"))
    protection = result.metadata["super_order"]["protection"]
    assert protection["exposed_quantity"] == 25
    assert protection["stop_loss_present"] is False
    assert protection["protected"] is False


def test_dhan_super_order_undercovered_stop_is_unprotected(monkeypatch):
    import asyncio
    from Backend.infrastructure.broker import dhan_order_adapter

    monkeypatch.setattr(dhan_order_adapter, "dhan_credentials", lambda: {"client_id": "x", "access_token": "y"})
    client = dhan_order_adapter.DhanBrokerClient()

    async def fake_orders():
        return [{
            "orderId": "SUPER-UNDERCOVERED-1", "orderStatus": "PART_TRADED",
            "quantity": 25, "filledQty": 10, "remainingQuantity": 15,
            "legDetails": [
                {"orderId": "SL-3", "legName": "STOP_LOSS_LEG", "orderStatus": "PENDING",
                 "totalQuatity": 5, "triggeredQuantity": 5, "price": 95},
            ],
        }]
    monkeypatch.setattr(client, "get_super_orders", fake_orders)

    result = asyncio.run(client.get_super_order_status("SUPER-UNDERCOVERED-1"))
    protection = result.metadata["super_order"]["protection"]
    assert protection["exposed_quantity"] == 10
    assert protection["stop_loss_active"] is False
    assert protection["protected"] is False


def test_dhan_super_order_terminal_stop_leg_is_not_active_protection(monkeypatch):
    import asyncio
    import pytest
    from Backend.infrastructure.broker import dhan_order_adapter

    monkeypatch.setattr(dhan_order_adapter, "dhan_credentials", lambda: {
        "client_id": "x", "access_token": "y"
    })
    client = dhan_order_adapter.DhanBrokerClient()

    async def fake_orders():
        return [{
            "orderId": "SUPER-STOP-TERMINAL", "orderStatus": "PART_TRADED",
            "quantity": 25, "filledQty": 10, "remainingQuantity": 15,
            "legName": "ENTRY_LEG",
            "legDetails": [{
                "orderId": "SL-TERMINAL", "legName": "STOP_LOSS_LEG",
                "orderStatus": "TRADED", "totalQuatity": 10,
                "remainingQuantity": 0, "triggeredQuantity": 10, "price": 95,
            }],
        }]

    monkeypatch.setattr(client, "get_super_orders", fake_orders)
    result = asyncio.run(client.get_super_order_status("SUPER-STOP-TERMINAL"))
    assert result is not None
    protection = result.metadata["super_order"]["protection"]
    assert protection["stop_loss_active"] is False
    assert protection["protected"] is False
