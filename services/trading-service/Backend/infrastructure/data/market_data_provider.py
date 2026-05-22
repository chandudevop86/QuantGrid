from __future__ import annotations

import json
import logging
import os
import time
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
logger = logging.getLogger(__name__)


def _redis_client() -> Any | None:
    url = os.getenv("REDIS_URL") or os.getenv("QUANTGRID_REDIS_URL")
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, socket_connect_timeout=0.2, socket_timeout=0.2)
    except Exception as exc:
        logger.warning("Redis cache unavailable: %s", exc)
        return None


def _cache_key(provider: str, symbol: str, interval: str, period: str) -> str:
    return f"quantgrid:market:{provider}:{symbol}:{interval}:{period}"


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
    retries = 2

    def fetch_chart(self, symbol: str, *, interval: str = "1m", period: str = "1d") -> dict[str, Any]:
        yahoo_symbol = market_symbol(symbol)
        cache = _redis_client()
        key = _cache_key(self.provider_name, yahoo_symbol, interval, period)
        if cache is not None:
            try:
                cached = cache.get(key)
                if cached:
                    chart = json.loads(cached.decode("utf-8"))
                    chart["cache_status"] = "redis-hit"
                    return chart
            except Exception as exc:
                logger.warning("Redis cache read failed: %s", exc)
        params = urlencode({
            "range": period,
            "interval": interval,
            "includePrePost": "false",
        })
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(yahoo_symbol, safe='')}?{params}"
        request = Request(url, headers={"User-Agent": "QuantGrid/1.0"})

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                started = time.monotonic()
                with urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                elapsed_ms = round((time.monotonic() - started) * 1000)
                result = payload.get("chart", {}).get("result") or []
                if not result:
                    error = payload.get("chart", {}).get("error") or "No market data returned"
                    raise RuntimeError(str(error))

                result[0]["provider_latency_ms"] = elapsed_ms
                result[0]["cache_status"] = "miss"
                if cache is not None:
                    try:
                        cache.setex(key, int(os.getenv("QUANTGRID_MARKET_CACHE_TTL_SECONDS", "10")), json.dumps(result[0]))
                    except Exception as exc:
                        logger.warning("Redis cache write failed: %s", exc)
                return result[0]
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    logger.warning("Yahoo fetch retry %s/%s for %s: %s", attempt + 1, self.retries, yahoo_symbol, exc)
                    time.sleep(0.25 * (attempt + 1))

        raise RuntimeError(str(last_error or "Yahoo market data fetch failed"))


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
