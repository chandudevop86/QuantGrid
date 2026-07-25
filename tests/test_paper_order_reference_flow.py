from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from Backend.application.order_management import OrderManagementService
from Backend.domain.models.order import Order
from Backend.domain.models.signal import StrategySignal


@dataclass
class PaperResult:
    broker_order_id: str
    status: str = "filled"


class DeterministicPaperBroker:
    def __init__(self) -> None:
        self.orders: list[Order] = []

    async def place_order(self, order: Order) -> PaperResult:
        self.orders.append(order)
        return PaperResult(broker_order_id="PAPER-REFERENCE-1")


def reference_signal() -> StrategySignal:
    return StrategySignal(
        strategy_name="paper_reference",
        symbol="NIFTY",
        side="BUY",
        entry_price=100.0,
        stop_loss=95.0,
        target_price=110.0,
        signal_time=datetime(2026, 7, 25, 9, 30, tzinfo=timezone.utc),
        metadata={"quantity": 1},
    )


def test_reference_signal_passes_risk_submits_once_and_records_audit() -> None:
    broker = DeterministicPaperBroker()
    service = OrderManagementService(broker)
    context = {
        "trades_today": 0,
        "daily_pnl": 0,
        "capital_per_trade": 10_000,
        "open_positions": 0,
        "market_data_age_seconds": 5,
        "vix": 14,
    }

    first = asyncio.run(service.submit_signal(reference_signal(), context))
    duplicate = asyncio.run(service.submit_signal(reference_signal(), context))

    assert first.accepted is True
    assert first.status == "filled"
    assert first.broker_order_id == "PAPER-REFERENCE-1"
    assert len(broker.orders) == 1
    assert broker.orders[0].metadata["correlation_id"].startswith("OMS-")
    assert [event["event"] for event in first.audit_trail] == [
        "risk_checked",
        "broker_submit_attempt",
        "broker_response",
    ]
    assert duplicate.accepted is False
    assert "DUPLICATE_TRADE" in duplicate.risk["blocked_by"]
    assert len(broker.orders) == 1
