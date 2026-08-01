from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Protocol
from uuid import UUID


class PortfolioRepository(ABC):
    """Port for Portfolio persistence. Implemented in infrastructure/repositories."""

    @abstractmethod
    async def create(self, **kwargs): ...

    @abstractmethod
    async def get_by_id(self, portfolio_id: UUID): ...

    @abstractmethod
    async def get_by_name_for_user(self, user_id: UUID, name: str): ...

    @abstractmethod
    async def list_for_user(self, user_id: UUID, *, offset: int, limit: int,
                             portfolio_type: str | None = None,
                             sort_by: str = "created_at", sort_dir: str = "desc"): ...

    @abstractmethod
    async def count_for_user(self, user_id: UUID, *, portfolio_type: str | None = None) -> int: ...

    @abstractmethod
    async def update(self, portfolio, **kwargs): ...

    @abstractmethod
    async def delete(self, portfolio) -> None: ...


class HoldingRepository(ABC):
    """Port for Holding persistence."""

    @abstractmethod
    async def create(self, **kwargs): ...

    @abstractmethod
    async def get_by_id(self, holding_id: UUID): ...

    @abstractmethod
    async def get_by_symbol(self, portfolio_id: UUID, symbol: str): ...

    @abstractmethod
    async def list_for_portfolio(self, portfolio_id: UUID, *, offset: int, limit: int,
                                  sector: str | None = None,
                                  sort_by: str = "symbol", sort_dir: str = "asc"): ...

    @abstractmethod
    async def count_for_portfolio(self, portfolio_id: UUID, *, sector: str | None = None) -> int: ...

    @abstractmethod
    async def update(self, holding, **kwargs): ...

    @abstractmethod
    async def delete(self, holding) -> None: ...


class TransactionRepository(ABC):
    """Port for Transaction persistence."""

    @abstractmethod
    async def create(self, **kwargs): ...

    @abstractmethod
    async def get_by_id(self, transaction_id: UUID): ...

    @abstractmethod
    async def list_for_portfolio(self, portfolio_id: UUID, *, offset: int, limit: int,
                                  symbol: str | None = None,
                                  transaction_type: str | None = None,
                                  start_date: date | None = None,
                                  end_date: date | None = None,
                                  sort_by: str = "transaction_date", sort_dir: str = "desc"): ...

    @abstractmethod
    async def count_for_portfolio(self, portfolio_id: UUID, **filters) -> int: ...

    @abstractmethod
    async def list_all_for_symbol(self, portfolio_id: UUID, symbol: str): ...

    @abstractmethod
    async def delete(self, transaction) -> None: ...


class WatchlistRepository(ABC):
    """Port for Watchlist persistence."""

    @abstractmethod
    async def create(self, **kwargs): ...

    @abstractmethod
    async def get_by_id(self, watchlist_id: UUID): ...

    @abstractmethod
    async def list_for_user(self, user_id: UUID, *, offset: int, limit: int): ...

    @abstractmethod
    async def count_for_user(self, user_id: UUID) -> int: ...

    @abstractmethod
    async def update(self, watchlist, **kwargs): ...

    @abstractmethod
    async def delete(self, watchlist) -> None: ...

    @abstractmethod
    async def add_item(self, watchlist_id: UUID, symbol: str, notes: str | None = None): ...

    @abstractmethod
    async def remove_item(self, watchlist_id: UUID, symbol: str) -> None: ...


class AlertRepository(ABC):
    """Port for Alert persistence."""

    @abstractmethod
    async def create(self, **kwargs): ...

    @abstractmethod
    async def get_by_id(self, alert_id: UUID): ...

    @abstractmethod
    async def list_for_user(self, user_id: UUID, *, offset: int, limit: int,
                             status: str | None = None,
                             alert_type: str | None = None): ...

    @abstractmethod
    async def count_for_user(self, user_id: UUID, **filters) -> int: ...

    @abstractmethod
    async def list_active(self): ...

    @abstractmethod
    async def update(self, alert, **kwargs): ...

    @abstractmethod
    async def delete(self, alert) -> None: ...


class MarketDataProvider(Protocol):
    """
    Port for external market-data access (live quotes + historical price series).
    Implemented by an infrastructure adapter (e.g. Redis-cached HTTP client to a
    market data vendor). Kept as a `Protocol` since it's an external service
    integration rather than a persistence repository.
    """

    async def get_latest_price(self, symbol: str) -> float: ...

    async def get_price_history(self, symbol: str, start_date: date, end_date: date) -> list[tuple[date, float]]: ...

    async def get_security_metadata(self, symbol: str) -> dict: ...
