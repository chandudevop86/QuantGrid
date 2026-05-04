from __future__ import annotations

from typing import Protocol

from app.domain.models.order import Order


class BrokerClient(Protocol):
    def place_order(self, order: Order) -> str:
        raise NotImplementedError


class PaperBrokerClient:
    def __init__(self) -> None:
        self.orders: list[Order] = []

    def place_order(self, order: Order) -> str:
        self.orders.append(order)
        return f"PAPER-{len(self.orders)}"
