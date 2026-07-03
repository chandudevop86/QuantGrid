from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Iterable

from Backend.domain.shared import IMarketDataProvider


class MarketDataProviderError(RuntimeError):
    pass


class MarketDataProvider(IMarketDataProvider, ABC):
    provider_name: str
    live_suitable: bool = False
    paper_suitable: bool = True
    warning: str | None = None
    latest_fetch_at: str | None = None

    @abstractmethod
    def get_ltp(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError

    def get_latest_price(self, symbol: str) -> dict[str, Any]:
        return self.get_ltp(symbol)

    @abstractmethod
    def get_candles(self, symbol: str, interval: str, period: str, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def subscribe_ticks(self, symbols: Iterable[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def normalize_symbol(self, symbol: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        raise NotImplementedError

    def get_market_status(self, symbol: str) -> dict[str, Any]:
        return self.health_check() | {"symbol": symbol.upper()}

    def candles(self, symbol: str, interval: str, limit: int = 100) -> list[dict[str, Any]]:
        return self.get_candles(symbol=symbol, interval=interval, period="1d", limit=limit)

    def status(self, symbol: str, interval: str) -> dict[str, Any]:
        return self.health_check() | {
            "symbol": symbol.upper(),
            "interval": interval,
            "latest_fetch_at": self.latest_fetch_at,
        }

    def mark_fetch(self) -> str:
        self.latest_fetch_at = datetime.now(timezone.utc).isoformat()
        return self.latest_fetch_at

    def status_payload(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "provider_name": self.provider_name,
            "live_suitable": self.live_suitable,
            "paper_suitable": self.paper_suitable,
            "latest_fetch_at": self.latest_fetch_at,
            "warning": self.warning,
        }
