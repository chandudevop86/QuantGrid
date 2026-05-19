from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4


@dataclass(slots=True)
class BrokerOrder:
    order_id: str
    symbol: str
    side: str
    qty: int
    price: float
    status: str = "pending"
    filled_price: float | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class BrokerInterface(Protocol):
    async def place_order(self, symbol: str, side: str, qty: int, price: float) -> BrokerOrder:
        raise NotImplementedError

    async def cancel_order(self, order_id: str) -> BrokerOrder:
        raise NotImplementedError

    async def get_order_status(self, order_id: str) -> BrokerOrder:
        raise NotImplementedError


class MockBroker:
    def __init__(self, *, fill_ratio: float = 1.0, reject_orders: bool = False, delay_ms: int = 0) -> None:
        self.fill_ratio = max(0.0, min(float(fill_ratio), 1.0))
        self.reject_orders = reject_orders
        self.delay_ms = max(0, int(delay_ms))
        self.orders: dict[str, BrokerOrder] = {}

    async def place_order(self, symbol: str, side: str, qty: int, price: float) -> BrokerOrder:
        if self.delay_ms:
            await asyncio.sleep(self.delay_ms / 1000.0)

        order = BrokerOrder(
            order_id=f"MOCK-{uuid4().hex[:12]}",
            symbol=symbol,
            side=side.upper(),
            qty=max(0, int(qty * self.fill_ratio)),
            price=float(price),
            status="rejected" if self.reject_orders else "filled",
            filled_price=None if self.reject_orders else float(price),
        )
        self.orders[order.order_id] = order
        return order

    async def cancel_order(self, order_id: str) -> BrokerOrder:
        order = self.orders[order_id]
        if order.status == "pending":
            order.status = "cancelled"
            order.updated_at = datetime.utcnow()
        return order

    async def get_order_status(self, order_id: str) -> BrokerOrder:
        return self.orders[order_id]


class ZerodhaBrokerAdapter:
    def __init__(self, kite_client: Any, *, exchange: str = "NSE", product: str = "MIS", order_type: str = "LIMIT") -> None:
        self.kite = kite_client
        self.exchange = exchange
        self.product = product
        self.order_type = order_type

    async def place_order(self, symbol: str, side: str, qty: int, price: float) -> BrokerOrder:
        transaction_type = "BUY" if side.upper() == "BUY" else "SELL"
        order_id = await asyncio.to_thread(
            self.kite.place_order,
            variety=getattr(self.kite, "VARIETY_REGULAR", "regular"),
            exchange=self.exchange,
            tradingsymbol=symbol,
            transaction_type=transaction_type,
            quantity=int(qty),
            product=self.product,
            order_type=self.order_type,
            price=float(price),
        )
        return BrokerOrder(order_id=str(order_id), symbol=symbol, side=transaction_type, qty=int(qty), price=float(price))

    async def cancel_order(self, order_id: str) -> BrokerOrder:
        await asyncio.to_thread(self.kite.cancel_order, variety=getattr(self.kite, "VARIETY_REGULAR", "regular"), order_id=order_id)
        return await self.get_order_status(order_id)

    async def get_order_status(self, order_id: str) -> BrokerOrder:
        history = await asyncio.to_thread(self.kite.order_history, order_id)
        latest = history[-1] if history else {}
        return BrokerOrder(
            order_id=str(order_id),
            symbol=str(latest.get("tradingsymbol", "")),
            side=str(latest.get("transaction_type", "")),
            qty=int(latest.get("quantity") or 0),
            price=float(latest.get("price") or 0.0),
            status=str(latest.get("status", "pending")).lower(),
            filled_price=float(latest["average_price"]) if latest.get("average_price") else None,
            metadata={"raw": latest},
        )
