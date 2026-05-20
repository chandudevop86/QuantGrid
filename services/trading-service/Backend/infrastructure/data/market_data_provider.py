from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from Backend.core.config import get_settings

YAHOO_SYMBOLS = {
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "NIFTY_50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "NIFTYBANK": "^NSEBANK",
}

YAHOO_TRADING_GRADE_WARNING = "Yahoo data is not trading-grade and should not be used for live execution."


def market_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace(" ", "").replace("-", "_")
    return YAHOO_SYMBOLS.get(normalized, symbol.upper())


class MarketDataProvider(ABC):
    provider_name: str
    warning: str | None = None

    @abstractmethod
    def fetch_chart(self, symbol: str, *, interval: str = "1m", period: str = "1d") -> dict[str, Any]:
        raise NotImplementedError


class YahooMarketDataProvider(MarketDataProvider):
    provider_name = "yahoo-finance"
    warning = YAHOO_TRADING_GRADE_WARNING

    def fetch_chart(self, symbol: str, *, interval: str = "1m", period: str = "1d") -> dict[str, Any]:
        yahoo_symbol = market_symbol(symbol)
        params = urlencode({
            "range": period,
            "interval": interval,
            "includePrePost": "false",
        })
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(yahoo_symbol, safe='')}?{params}"
        request = Request(url, headers={"User-Agent": "QuantGrid/1.0"})

        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        result = payload.get("chart", {}).get("result") or []
        if not result:
            error = payload.get("chart", {}).get("error") or "No market data returned"
            raise RuntimeError(str(error))

        return result[0]


class FutureBrokerMarketDataProvider(MarketDataProvider):
    provider_name = "broker"
    warning = None

    def fetch_chart(self, symbol: str, *, interval: str = "1m", period: str = "1d") -> dict[str, Any]:
        raise NotImplementedError("Broker market data provider is not configured yet.")


def get_market_data_provider() -> MarketDataProvider:
    provider = get_settings().market_data_provider
    if provider == "yahoo":
        return YahooMarketDataProvider()
    if provider == "broker":
        return FutureBrokerMarketDataProvider()
    raise RuntimeError(f"Unsupported market data provider: {provider}")
