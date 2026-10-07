from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from Backend.core.config import get_settings
from Backend.infrastructure.broker.dhan_status import dhan_credentials
from Backend.infrastructure.broker.registry import create_broker_adapter
from Backend.domain.models.order import Order
from Backend.domain.shared import IBrokerAdapter
from Backend.config import Provider

@dataclass(frozen=True, slots=True)
class BrokerCapabilities:
    provider: str
    place_order: bool
    order_status: bool
    order_book: bool
    positions: bool
    modify_order: bool
    cancel_order: bool
    correlation_lookup: bool
    partial_fills: bool
    protected_order_submission: bool
    broker_native_protective_stop: bool

    @property
    def reconciliation_ready(self) -> bool:
        return bool(self.order_status and self.order_book and self.positions and self.correlation_lookup)

    @property
    def live_execution_ready(self) -> bool:
        return bool(
            self.place_order
            and self.reconciliation_ready
            and self.modify_order
            and self.cancel_order
            and self.partial_fills
            and self.broker_native_protective_stop
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "reconciliation_ready": self.reconciliation_ready,
            "live_execution_ready": self.live_execution_ready,
        }


def broker_capabilities(client: Any) -> BrokerCapabilities:
    provider = str((client.status() or {}).get("provider") or client.__class__.__name__).lower()
    return BrokerCapabilities(
        provider=provider,
        place_order=callable(getattr(client, "place_order", None)),
        order_status=callable(getattr(client, "get_order_status", None)),
        order_book=callable(getattr(client, "get_order_book", None)),
        positions=callable(getattr(client, "get_positions", None)),
        modify_order=callable(getattr(client, "modify_order", None)),
        cancel_order=callable(getattr(client, "cancel_order", None)),
        correlation_lookup=callable(getattr(client, "find_order_by_correlation_id", None)),
        partial_fills=bool(getattr(client, "supports_partial_fills", False)),
        protected_order_submission=bool(getattr(client, "supports_protected_order_submission", False)),
        broker_native_protective_stop=bool(getattr(client, "supports_broker_native_protective_stop", False)),
    )


@dataclass(slots=True)
class BrokerOrderResult:
    broker_order_id: str
    status: str
    symbol: str
    side: str
    quantity: int
    filled_quantity: int = 0
    remaining_quantity: int = 0
    price: float | None = None
    message: str = ""
    confirmed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BrokerClient(IBrokerAdapter, Protocol):
    async def authenticate(self) -> dict[str, Any]:
        raise NotImplementedError

    async def get_margin(self) -> dict[str, Any]:
        raise NotImplementedError

    async def place_order(self, order: Order) -> BrokerOrderResult:
        raise NotImplementedError

    async def modify_order(self, broker_order_id: str, updates: dict[str, Any]) -> BrokerOrderResult:
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
    supports_partial_fills = False
    supports_protected_order_submission = False
    supports_broker_native_protective_stop = False

    def __init__(self) -> None:
        self.orders: dict[str, BrokerOrderResult] = {}

    async def authenticate(self) -> dict[str, Any]:
        return {"authenticated": True, "provider": "paper", "live": False}

    async def get_margin(self) -> dict[str, Any]:
        return {"available": 10_000_000.0, "used": 0.0, "currency": "INR", "provider": "paper"}

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

    async def modify_order(self, broker_order_id: str, updates: dict[str, Any]) -> BrokerOrderResult:
        order = await self.get_order_status(broker_order_id)
        if order.status == "not_found":
            return order
        if "quantity" in updates and updates["quantity"] is not None:
            order.quantity = int(updates["quantity"])
        if "price" in updates:
            order.price = float(updates["price"]) if updates["price"] is not None else None
        order.message = "Paper order modified."
        return order

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

    async def get_order_book(self) -> list[dict[str, Any]]:
        return [order.to_dict() for order in self.orders.values()]

    def status(self) -> dict[str, Any]:
        return {
            "provider": "paper",
            "configured": True,
            "connected": True,
            "live": False,
            "orders": len(self.orders),
        }


class LiveBrokerClient:
    async def authenticate(self) -> dict[str, Any]:
        raise RuntimeError("Live broker authentication is not implemented. Configure a concrete broker adapter first.")

    async def get_margin(self) -> dict[str, Any]:
        raise RuntimeError("Live broker margin is not implemented. Configure a concrete broker adapter first.")

    async def place_order(self, order: Order) -> BrokerOrderResult:
        raise RuntimeError("Live broker execution is not implemented. Configure a concrete broker adapter first.")

    async def modify_order(self, broker_order_id: str, updates: dict[str, Any]) -> BrokerOrderResult:
        raise RuntimeError("Live broker order modification is not implemented. Configure a concrete broker adapter first.")

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        raise RuntimeError("Live broker cancellation is not implemented. Configure a concrete broker adapter first.")

    async def get_order_status(self, broker_order_id: str) -> BrokerOrderResult:
        raise RuntimeError("Live broker order status is not implemented. Configure a concrete broker adapter first.")

    async def get_positions(self) -> list[dict[str, Any]]:
        raise RuntimeError("Live broker positions are not implemented. Configure a concrete broker adapter first.")

    async def get_holdings(self) -> list[dict[str, Any]]:
        raise RuntimeError("Live broker holdings are not implemented. Configure a concrete broker adapter first.")

    async def get_order_book(self) -> list[dict[str, Any]]:
        raise RuntimeError("Live broker order book is not implemented. Configure a concrete broker adapter first.")

    def status(self) -> dict[str, Any]:
        settings = get_settings()
        return {
            "provider": settings.broker_provider or "live",
            "configured": settings.broker_configured,
            "connected": False,
            "live": True,
            "message": "Concrete live broker adapter is not configured.",
        }


_PAPER_BROKER = PaperBrokerClient()


def broker_client_for_mode(mode: str) -> BrokerClient:
    settings = get_settings()
    if mode == "paper":
        return _PAPER_BROKER
    if mode != "live":
        raise RuntimeError("Invalid broker mode.")
    if not settings.live_trading_enabled:
        raise RuntimeError("Live broker is disabled. Set QUANTGRID_ENABLE_LIVE_TRADING=true to enable live broker integration.")
    if not getattr(settings, "live_money_approved", False):
        raise RuntimeError("Live broker is disabled until QUANTGRID_LIVE_MONEY_APPROVED=true is set after separate real-money authorization.")
    if not settings.broker_live_enabled:
        raise RuntimeError("Live broker is disabled. Set BROKER_LIVE_ENABLED=true to enable live broker integration.")
    if not settings.broker_configured:
        raise RuntimeError("Live broker requires broker provider and credentials.")
    provider = str(settings.broker_provider or "").strip().lower()
    if not provider and _dhan_configured(settings):
        provider = Provider.DHAN
    if provider:
        return create_broker_adapter(provider)
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


def _dhan_configured(settings: Any) -> bool:
    provider = str(getattr(settings, "broker_provider", "") or "").strip().lower()
    credentials = dhan_credentials()
    return bool(
        provider == Provider.DHAN
        or (credentials.get("client_id") and credentials.get("access_token"))
    )
