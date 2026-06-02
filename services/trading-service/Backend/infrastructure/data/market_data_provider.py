from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
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
    live_suitable: bool = False
    paper_suitable: bool = True
    latest_fetch_at: str | None = None

    @abstractmethod
    def fetch_chart(self, symbol: str, *, interval: str = "1m", period: str = "1d") -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_latest_price(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_candles(self, symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_market_status(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError

    def _mark_fetch(self) -> str:
        self.latest_fetch_at = datetime.now(timezone.utc).isoformat()
        return self.latest_fetch_at

    def status_payload(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "provider_name": self.provider_name,
            "live_suitable": self.live_suitable,
            "paper_suitable": self.paper_suitable,
            "latest_fetch_at": self.latest_fetch_at,
            "fresh": False,
            "stale": True,
            "warning": self.warning,
        }


class YahooMarketDataProvider(MarketDataProvider):
    provider_name = "yahoo-finance"
    warning = YAHOO_TRADING_GRADE_WARNING
    live_suitable = False
    paper_suitable = True
    retries = 2

    def fetch_chart(self, symbol: str, *, interval: str = "1m", period: str = "1d") -> dict[str, Any]:
        self._mark_fetch()
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

    def get_latest_price(self, symbol: str) -> dict[str, Any]:
        chart = self.fetch_chart(symbol, interval="1m", period="1d")
        meta = chart.get("meta", {})
        price = meta.get("regularMarketPrice")
        return {
            "symbol": symbol.upper(),
            "market_symbol": meta.get("symbol", market_symbol(symbol)),
            "price": round(float(price), 2) if price not in {None, ""} else None,
            "timestamp": self.latest_fetch_at,
            "source": self.provider_name,
            "exchange_timezone": meta.get("timezone"),
            "provider_latency_ms": chart.get("provider_latency_ms"),
            "provider_warning": self.warning,
        }

    def get_candles(self, symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
        chart = self.fetch_chart(symbol, interval=interval, period="1d")
        timestamps = chart.get("timestamp") or []
        quote_data = (chart.get("indicators", {}).get("quote") or [{}])[0]
        opens = quote_data.get("open") or []
        highs = quote_data.get("high") or []
        lows = quote_data.get("low") or []
        closes = quote_data.get("close") or []
        volumes = quote_data.get("volume") or []
        timezone_name = chart.get("meta", {}).get("timezone", "Asia/Kolkata")
        candles: list[dict[str, Any]] = []
        for index, timestamp in enumerate(timestamps):
            values = [
                opens[index] if index < len(opens) else None,
                highs[index] if index < len(highs) else None,
                lows[index] if index < len(lows) else None,
                closes[index] if index < len(closes) else None,
            ]
            if any(value is None for value in values):
                continue
            candles.append({
                "symbol": symbol.upper(),
                "timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                "exchange_timezone": timezone_name,
                "open": round(float(values[0]), 2),
                "high": round(float(values[1]), 2),
                "low": round(float(values[2]), 2),
                "close": round(float(values[3]), 2),
                "volume": int(volumes[index] or 0) if index < len(volumes) else 0,
            })
        return candles[-max(1, min(int(limit), 500)):]

    def get_market_status(self, symbol: str) -> dict[str, Any]:
        return self.status_payload() | {"symbol": symbol.upper()}


class FutureBrokerMarketDataProvider(MarketDataProvider):
    provider_name = "broker"
    warning = None
    live_suitable = True
    paper_suitable = True

    def fetch_chart(self, symbol: str, *, interval: str = "1m", period: str = "1d") -> dict[str, Any]:
        raise NotImplementedError("Broker market data provider is not configured yet.")

    def get_latest_price(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError("Broker latest price adapter is not configured yet.")

    def get_candles(self, symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError("Broker candle adapter is not configured yet.")

    def get_market_status(self, symbol: str) -> dict[str, Any]:
        return self.status_payload() | {
            "symbol": symbol.upper(),
            "warning": "Broker/NSE-grade market data adapter is selected but not configured.",
        }


class FutureNseMarketDataProvider(FutureBrokerMarketDataProvider):
    provider_name = "nse"

    def fetch_chart(self, symbol: str, *, interval: str = "1m", period: str = "1d") -> dict[str, Any]:
        raise NotImplementedError("NSE-grade market data provider is not configured yet.")

    def get_latest_price(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError("NSE-grade latest price adapter is not configured yet.")

    def get_candles(self, symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError("NSE-grade candle adapter is not configured yet.")

    def get_market_status(self, symbol: str) -> dict[str, Any]:
        return self.status_payload() | {
            "symbol": symbol.upper(),
            "warning": "NSE-grade market data adapter is selected but not configured.",
        }


def get_market_data_provider() -> MarketDataProvider:
    provider = get_settings().market_data_provider
    if provider == "yahoo":
        return YahooMarketDataProvider()
    if provider in {"broker", "dhan"}:
        return FutureBrokerMarketDataProvider()
    if provider == "nse":
        return FutureNseMarketDataProvider()
    raise RuntimeError(f"Unsupported market data provider: {provider}")
