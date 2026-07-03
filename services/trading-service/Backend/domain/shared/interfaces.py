from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from Backend.domain.models.context import StrategyContext
from Backend.domain.models.order import Order
from Backend.domain.models.signal import StrategySignal


@runtime_checkable
class IMarketDataProvider(Protocol):
    def candles(self, symbol: str, interval: str, limit: int = 100) -> list[dict[str, Any]]:
        ...

    def status(self, symbol: str, interval: str) -> dict[str, Any]:
        ...


@runtime_checkable
class IStrategy(Protocol):
    name: str

    def run(self, data: Any, context: StrategyContext) -> list[StrategySignal]:
        ...

    def generate_signal(self, candles: Any, context: StrategyContext) -> list[StrategySignal]:
        ...

    def validate_inputs(self, candles: Any, context: StrategyContext) -> None:
        ...

    def explain_signal(self, signal: StrategySignal) -> str:
        ...


@runtime_checkable
class IRiskManager(Protocol):
    def validate(self, signal: StrategySignal, context: dict[str, Any]) -> dict[str, Any]:
        ...


@runtime_checkable
class IBrokerAdapter(Protocol):
    async def authenticate(self) -> dict[str, Any]:
        ...

    async def get_margin(self) -> dict[str, Any]:
        ...

    async def get_positions(self) -> list[dict[str, Any]]:
        ...

    async def place_order(self, order: Order) -> Any:
        ...

    async def modify_order(self, broker_order_id: str, updates: dict[str, Any]) -> Any:
        ...

    async def cancel_order(self, broker_order_id: str) -> Any:
        ...

    async def get_order_status(self, broker_order_id: str) -> Any:
        ...

    async def get_order_book(self) -> list[dict[str, Any]]:
        ...

    def status(self) -> dict[str, Any]:
        ...


@runtime_checkable
class IOrderManager(Protocol):
    def order_from_signal(self, signal: StrategySignal, *, quantity: int | None = None) -> Order:
        ...


@runtime_checkable
class INotificationService(Protocol):
    def notify(self, message: str, *, severity: str = "info", metadata: dict[str, Any] | None = None) -> None:
        ...


@runtime_checkable
class ITradeRepository(Protocol):
    def list_trades(self, symbol: str | None = None) -> list[dict[str, Any]]:
        ...

    def save_trade(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


@runtime_checkable
class IDecisionEngine(Protocol):
    def decide(self, inputs: Any) -> Any:
        ...


@runtime_checkable
class IAnalyticsService(Protocol):
    def trade_journal_summary(self, limit: int = 100) -> dict[str, Any]:
        ...

    def strategy_ranking(self, limit: int = 500) -> dict[str, Any]:
        ...
