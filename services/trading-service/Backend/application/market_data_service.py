from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from Backend.application.candle_validation import validate_live_candle
from Backend.application.monitoring import (
    observe_market_data_cache,
    observe_market_data_delay,
    observe_market_data_error,
    observe_market_data_tick,
)
from Backend.core.config import get_settings
from Backend.domain.market_data.provider import MarketDataProvider, MarketDataProviderError
from Backend.infrastructure.market_data import AngelProvider, DhanProvider, FyersProvider, KiteProvider, UpstoxProvider, YahooProvider


_MEMORY_CACHE: dict[str, tuple[float, Any]] = {}


def cache_ttl_seconds() -> int:
    try:
        return max(1, int(os.getenv("QUANTGRID_MARKET_CACHE_TTL_SECONDS", "5")))
    except ValueError:
        return 5


def redis_client() -> Any | None:
    url = os.getenv("REDIS_URL") or os.getenv("QUANTGRID_REDIS_URL")
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, socket_connect_timeout=0.2, socket_timeout=0.2)
    except Exception:
        return None


class MarketDataService:
    def __init__(self, provider: MarketDataProvider | None = None) -> None:
        self.settings = get_settings()
        self.provider = provider or select_market_data_provider(self.settings.market_data_provider)
        self.cache = redis_client()
        self.ttl = cache_ttl_seconds()

    def get_ltp(self, symbol: str, *, mode: str = "paper") -> dict[str, Any]:
        self._assert_provider_allowed(mode)
        key = self._cache_key("ltp", symbol.upper())
        cached = self._cache_get(key)
        if cached:
            observe_market_data_cache(self.provider.provider_name, "ltp", True)
            return {**cached, "cache_status": "fresh"}
        observe_market_data_cache(self.provider.provider_name, "ltp", False)
        try:
            payload = self.provider.get_ltp(symbol)
        except Exception:
            observe_market_data_error(self.provider.provider_name, "ltp")
            if mode != "live":
                stale = self._cache_get(key, allow_expired=True)
                if stale and self._is_fresh(stale.get("timestamp")):
                    return {**stale, "cache_status": "fresh"}
            raise
        normalized = self._normalize_ltp_payload(symbol, payload)
        self._validate_ltp(normalized, mode=mode)
        self._cache_set(key, normalized)
        observe_market_data_tick(self.provider.provider_name, symbol)
        observe_market_data_delay(self.provider.provider_name, symbol, normalized.get("feed_delay_seconds"))
        return {**normalized, "cache_status": "fresh"}

    def get_candles(self, symbol: str, interval: str, period: str = "1d", limit: int = 100, *, mode: str = "paper") -> dict[str, Any]:
        self._assert_provider_allowed(mode)
        limit = max(1, min(int(limit), 500))
        key = self._cache_key("candles", symbol.upper(), interval, period, str(limit))
        cached = self._cache_get(key)
        if cached:
            observe_market_data_cache(self.provider.provider_name, "candles", True)
            return {**cached, "cache_status": "fresh"}
        observe_market_data_cache(self.provider.provider_name, "candles", False)
        try:
            candles = self.provider.get_candles(symbol, interval, period, limit)
        except Exception:
            observe_market_data_error(self.provider.provider_name, "candles")
            if mode != "live":
                stale = self._cache_get(key, allow_expired=True)
                if stale and _candles_fresh(stale.get("candles", []), interval):
                    return {**stale, "cache_status": "fresh"}
            raise
        if not candles:
            raise MarketDataProviderError("Market data provider returned no candles.")
        fetched_at = getattr(self.provider, "latest_fetch_at", None) or _utc_now()
        validation = validate_live_candle(
            candles,
            interval=interval,
            mode="live" if mode == "live" else "paper",
            source=self.provider.provider_name,
            provider_fetched_at=fetched_at,
        )
        if mode == "live" and not validation.valid_for_execution:
            raise MarketDataProviderError(f"Live market feed is stale or invalid: {validation.market_status}")
        payload = {
            "provider": self.provider.provider_name,
            "provider_name": self.provider.provider_name,
            "symbol": symbol.upper(),
            "market_symbol": self.provider.normalize_symbol(symbol),
            "interval": interval,
            "period": period,
            "source": "live" if self.provider.live_suitable else "demo",
            "fetched_at": fetched_at,
            "latest_fetch_at": fetched_at,
            "candles": candles,
            "validation": validation.model_dump(),
            "fresh": validation.valid_for_analysis,
            "stale": not validation.valid_for_analysis,
            "feed_delay_seconds": validation.delay_seconds,
        }
        self._cache_set(key, payload)
        observe_market_data_delay(self.provider.provider_name, symbol, validation.delay_seconds)
        return {**payload, "cache_status": "fresh"}

    def health(self, symbol: str = "NIFTY", interval: str = "1m") -> dict[str, Any]:
        status = self.provider.health_check()
        errors: list[str] = []
        ltp_payload = None
        candle_payload = None
        try:
            ltp_payload = self.get_ltp(symbol, mode="paper")
        except Exception as exc:
            errors.append(str(exc))
        try:
            candle_payload = self.get_candles(symbol, interval, "1d", 100, mode="paper")
        except Exception as exc:
            errors.append(str(exc))
        latest_fetch_at = (
            (ltp_payload or {}).get("timestamp")
            or (candle_payload or {}).get("latest_fetch_at")
            or getattr(self.provider, "latest_fetch_at", None)
        )
        fresh = bool((ltp_payload or {}).get("cache_status") == "fresh" or (candle_payload or {}).get("fresh"))
        live_suitable = bool(self.provider.live_suitable and not errors)
        return status | {
            "configured_provider": self.settings.market_data_provider,
            "latest_fetch_at": latest_fetch_at,
            "last_tick_time": (ltp_payload or {}).get("timestamp"),
            "feed_delay_seconds": (ltp_payload or candle_payload or {}).get("feed_delay_seconds"),
            "cache_status": (ltp_payload or candle_payload or {}).get("cache_status", "miss"),
            "fresh": fresh and not errors,
            "stale": bool(errors) or not fresh,
            "live_suitable": live_suitable,
            "paper_suitable": self.provider.paper_suitable,
            "feed_status": _feed_status(self.provider, fresh=fresh and not errors, errors=errors),
            "errors": errors,
        }

    def _assert_provider_allowed(self, mode: str) -> None:
        live_mode = mode == "live" or self.settings.live_trading_enabled
        if live_mode and self.provider.provider_name == "yahoo" and not self.settings.allow_yahoo_for_live:
            raise MarketDataProviderError("Yahoo market data is demo/paper only and cannot be used for live trading.")

    def _normalize_ltp_payload(self, symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
        ltp = payload.get("ltp", payload.get("price"))
        timestamp = payload.get("timestamp") or _utc_now()
        delay = _feed_delay_seconds(timestamp)
        return {
            **payload,
            "provider": self.provider.provider_name,
            "provider_name": self.provider.provider_name,
            "symbol": symbol.upper(),
            "market_symbol": payload.get("market_symbol") or self.provider.normalize_symbol(symbol),
            "exchange": payload.get("exchange") or "NSE",
            "ltp": round(float(ltp), 2) if ltp not in {None, ""} else None,
            "price": round(float(ltp), 2) if ltp not in {None, ""} else None,
            "timestamp": timestamp,
            "source": "live" if self.provider.live_suitable else "demo",
            "feed_delay_seconds": delay,
            "provider_warning": payload.get("provider_warning") or self.provider.warning,
        }

    def _validate_ltp(self, payload: dict[str, Any], *, mode: str) -> None:
        if payload["ltp"] is None or float(payload["ltp"]) <= 0:
            raise MarketDataProviderError("Market data LTP is zero or missing.")
        if mode == "live":
            exchange_timezone = str(payload.get("exchange_timezone") or "")
            if exchange_timezone != "Asia/Kolkata":
                raise MarketDataProviderError(f"Live tick timezone must be Asia/Kolkata; got {exchange_timezone or 'unknown'}.")
            if not self._is_fresh(payload.get("timestamp")):
                raise MarketDataProviderError("Live tick is stale.")

    def _is_fresh(self, timestamp: Any) -> bool:
        delay = _feed_delay_seconds(timestamp)
        return delay is not None and delay <= self.ttl

    def _cache_key(self, *parts: str) -> str:
        return "quantgrid:market:" + ":".join([self.provider.provider_name, *parts])

    def _cache_get(self, key: str, *, allow_expired: bool = False) -> Any | None:
        if self.cache is not None:
            raw = self.cache.get(key)
            return json.loads(raw.decode("utf-8")) if raw else None
        item = _MEMORY_CACHE.get(key)
        if not item:
            return None
        expires_at, value = item
        if not allow_expired and datetime.now(timezone.utc).timestamp() > expires_at:
            _MEMORY_CACHE.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: Any) -> None:
        if self.cache is not None:
            self.cache.setex(key, self.ttl, json.dumps(value))
            return
        _MEMORY_CACHE[key] = (datetime.now(timezone.utc).timestamp() + self.ttl, value)


def select_market_data_provider(name: str) -> MarketDataProvider:
    provider = (name or "yahoo").strip().lower()
    if provider == "yahoo":
        return YahooProvider()
    if provider == "kite":
        return KiteProvider()
    if provider == "upstox":
        return UpstoxProvider()
    if provider == "dhan":
        return DhanProvider()
    if provider == "fyers":
        return FyersProvider()
    if provider in {"angel", "smartapi", "angelone"}:
        return AngelProvider()
    raise MarketDataProviderError(f"Unsupported market data provider: {provider}")


def get_market_data_service() -> MarketDataService:
    return MarketDataService()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _feed_delay_seconds(timestamp: Any) -> int | None:
    if not timestamp:
        return None
    try:
        parsed = timestamp if isinstance(timestamp, datetime) else datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()))


def _candles_fresh(candles: list[dict[str, Any]], interval: str) -> bool:
    if not candles:
        return False
    validation = validate_live_candle(candles, interval=interval, mode="paper")
    return validation.valid_for_analysis


def _feed_status(provider: MarketDataProvider, *, fresh: bool, errors: list[str]) -> str:
    if provider.provider_name == "yahoo":
        return "DEMO/YAHOO MODE"
    if errors:
        return "FEED DOWN"
    if fresh:
        return "LIVE FEED"
    return "DELAYED FEED"
