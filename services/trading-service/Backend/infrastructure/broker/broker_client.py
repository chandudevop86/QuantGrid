from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from Backend.core.config import get_settings
from Backend.domain.models.order import Order


@dataclass(slots=True)
class BrokerOrderResult:
    broker_order_id: str
    status: str
    symbol: str
    side: str
    quantity: int
    price: float | None = None
    message: str = ""
    confirmed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BrokerClient(Protocol):
    async def place_order(self, order: Order) -> BrokerOrderResult:
        raise NotImplementedError

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        raise NotImplementedError

    async def get_order_status(self, broker_order_id: str) -> BrokerOrderResult:
        raise NotImplementedError

    async def get_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_holdings(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class PaperBrokerClient:
    def __init__(self) -> None:
        self.orders: dict[str, BrokerOrderResult] = {}

    async def place_order(self, order: Order) -> BrokerOrderResult:
        broker_order_id = f"PAPER-{uuid4().hex[:12]}"
        result = BrokerOrderResult(
            broker_order_id=broker_order_id,
            status="confirmed",
            symbol=order.symbol,
            side=order.side.upper(),
            quantity=int(order.quantity),
            price=float(order.price) if order.price is not None else None,
            message="Paper broker confirmed simulated order.",
            confirmed=True,
            metadata={"order": _order_metadata(order)},
        )
        self.orders[broker_order_id] = result
        return result

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        order = await self.get_order_status(broker_order_id)
        if order.status not in {"filled", "confirmed", "cancelled"}:
            order.status = "cancelled"
            order.message = "Paper order cancelled."
            order.confirmed = True
        return order

    async def get_order_status(self, broker_order_id: str) -> BrokerOrderResult:
        if broker_order_id not in self.orders:
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="not_found",
                symbol="",
                side="",
                quantity=0,
                message="Paper broker order was not found.",
                confirmed=False,
            )
        return self.orders[broker_order_id]

    async def get_positions(self) -> list[dict[str, Any]]:
        return [
            {
                "broker_order_id": order.broker_order_id,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.quantity,
                "price": order.price,
                "status": order.status,
            }
            for order in self.orders.values()
            if order.confirmed and order.status in {"confirmed", "filled"}
        ]

    async def get_holdings(self) -> list[dict[str, Any]]:
        return []


class LiveBrokerClient:
    async def place_order(self, order: Order) -> BrokerOrderResult:
        raise RuntimeError("Live broker execution is not implemented. Configure a concrete broker adapter first.")

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        raise RuntimeError("Live broker cancellation is not implemented. Configure a concrete broker adapter first.")

    async def get_order_status(self, broker_order_id: str) -> BrokerOrderResult:
        raise RuntimeError("Live broker order status is not implemented. Configure a concrete broker adapter first.")

    async def get_positions(self) -> list[dict[str, Any]]:
        raise RuntimeError("Live broker positions are not implemented. Configure a concrete broker adapter first.")

    async def get_holdings(self) -> list[dict[str, Any]]:
        raise RuntimeError("Live broker holdings are not implemented. Configure a concrete broker adapter first.")


_PAPER_BROKER = PaperBrokerClient()


def broker_client_for_mode(mode: str) -> BrokerClient:
    settings = get_settings()
    if mode == "paper":
        return _PAPER_BROKER
    if not settings.broker_live_enabled:
        raise RuntimeError("Live broker is disabled. Set BROKER_LIVE_ENABLED=true to enable live broker integration.")
    return LiveBrokerClient()


def _order_metadata(order: Order) -> dict[str, Any]:
    return {
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "order_type": order.order_type,
        "price": order.price,
        "stop_loss": order.stop_loss,
        "target_price": order.target_price,
        "metadata": order.metadata,
    }
