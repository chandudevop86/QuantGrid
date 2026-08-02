from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from Backend.application.order_management import OrderManagementService
from Backend.domain.models.order import Order
from Backend.domain.models.signal import StrategySignal


def _signal(**overrides) -> StrategySignal:
    data = {
        "strategy_name": "breakout",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "target_price": 110.0,
        "signal_time": datetime(2026, 7, 3, 9, 30, tzinfo=timezone.utc),
        "metadata": {"quantity": 1},
    }
    data.update(overrides)
    return StrategySignal(**data)


@dataclass
class FakeBrokerResult:
    broker_order_id: str
    status: str


class FakeBroker:
    def __init__(self, statuses: list[str] | None = None, fail_first: bool = False) -> None:
        self.statuses = statuses or ["confirmed"]
        self.fail_first = fail_first
        self.orders: list[Order] = []

    async def authenticate(self):
        return {"authenticated": True}

    async def get_margin(self):
        return {"available": 100000}

    async def place_order(self, order: Order):
        self.orders.append(order)
        if self.fail_first and len(self.orders) == 1:
            raise RuntimeError("temporary broker failure")
        status = self.statuses[min(len(self.orders) - 1, len(self.statuses) - 1)]
        return FakeBrokerResult(broker_order_id=f"mock-{len(self.orders)}", status=status)

    async def modify_order(self, broker_order_id: str, updates: dict):
        return FakeBrokerResult(broker_order_id=broker_order_id, status="modified")

    async def cancel_order(self, broker_order_id: str):
        return FakeBrokerResult(broker_order_id=broker_order_id, status="cancelled")

    async def get_order_status(self, broker_order_id: str):
        return FakeBrokerResult(broker_order_id=broker_order_id, status="confirmed")

    async def get_positions(self):
        return []

    async def get_order_book(self):
        return []

    def status(self):
        return {"provider": "fake", "connected": True}


def test_oms_submits_clean_signal_and_records_audit_trail():
    broker = FakeBroker()
    result = asyncio.run(
        OrderManagementService(broker).submit_signal(
            _signal(),
            {"trades_today": 0, "daily_pnl": 0, "capital_per_trade": 10000, "open_positions": 0, "market_data_age_seconds": 5, "vix": 14},
        )
    )

    assert result.accepted is True
    assert result.status == "submitted"
    assert result.broker_order_id == "mock-1"
    assert result.audit_trail[0]["event"] == "risk_checked"


def test_oms_prevents_duplicate_active_order():
    service = OrderManagementService(FakeBroker())
    context = {"trades_today": 0, "daily_pnl": 0, "capital_per_trade": 10000, "open_positions": 0, "market_data_age_seconds": 5, "vix": 14}

    first = asyncio.run(service.submit_signal(_signal(), context))
    second = asyncio.run(service.submit_signal(_signal(), context))

    assert first.accepted is True
    assert second.accepted is False
    assert "DUPLICATE_TRADE" in second.risk["blocked_by"]


def test_oms_retries_temporary_broker_failure():
    broker = FakeBroker(fail_first=True)
    result = asyncio.run(
        OrderManagementService(broker, max_retries=1).submit_signal(
            _signal(),
            {"trades_today": 0, "daily_pnl": 0, "capital_per_trade": 10000, "open_positions": 0, "market_data_age_seconds": 5, "vix": 14},
        )
    )

    assert result.accepted is True
    assert result.attempts == 2
    assert len(broker.orders) == 2


def test_oms_handles_rejected_and_partial_fills():
    context = {"trades_today": 0, "daily_pnl": 0, "capital_per_trade": 10000, "open_positions": 0, "market_data_age_seconds": 5, "vix": 14}

    rejected = asyncio.run(OrderManagementService(FakeBroker(["rejected"])).submit_signal(_signal(), context))
    partial = asyncio.run(OrderManagementService(FakeBroker(["partially_filled"])).submit_signal(_signal(), context))

    assert rejected.accepted is False
    assert rejected.status == "rejected"
    assert partial.accepted is True
    assert partial.status == "partially_filled"
