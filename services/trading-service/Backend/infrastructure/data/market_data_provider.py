from __future__ import annotations

from typing import Any

from Backend.application.market_data_service import select_market_data_provider
from Backend.core.config import get_settings
from Backend.domain.market_data.provider import MarketDataProvider
from Backend.infrastructure.market_data.yahoo_provider import (
    YAHOO_SYMBOLS,
    YAHOO_TRADING_GRADE_WARNING,
    YahooProvider,
)
from Backend.infrastructure.market_data.base import EnvConfiguredProvider
from Backend.infrastructure.market_data.dhan_provider import DhanProvider

from Backend.config import Provider


class YahooMarketDataProvider(YahooProvider):
    provider_name = "yahoo-finance"

    def get_latest_price(self, symbol: str) -> dict[str, Any]:
        payload = self.get_ltp(symbol)
        return {**payload, "source": "yahoo-finance"}

    def get_candles(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        return super().get_candles(symbol, interval, "1d", limit)

    def get_market_status(self, symbol: str) -> dict[str, Any]:
        return self.health_check() | {"symbol": symbol.upper()}


class FutureBrokerMarketDataProvider(EnvConfiguredProvider):
    provider_name = "broker"
    required_env: tuple[str, ...] = ()

    def get_latest_price(self, symbol: str) -> dict[str, Any]:
        return self.get_ltp(symbol)

    def get_candles(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        return super().get_candles(symbol, interval, "1d", limit)

    def get_market_status(self, symbol: str) -> dict[str, Any]:
        return self.health_check() | {"symbol": symbol.upper()}


class FutureNseMarketDataProvider(FutureBrokerMarketDataProvider):
    provider_name = "nse"


def market_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace(" ", "").replace("-", "_")
    return YAHOO_SYMBOLS.get(normalized, symbol.upper())


def get_market_data_provider() -> MarketDataProvider:
    provider = get_settings().market_data_provider.strip().lower()

    if provider == Provider.YAHOO:
        return YahooMarketDataProvider()

    if provider == "broker":
        return FutureBrokerMarketDataProvider()

    if provider == "nse":
        return FutureNseMarketDataProvider()

    if provider == Provider.DHAN:
        return DhanProvider()

    return select_market_data_provider(provider)