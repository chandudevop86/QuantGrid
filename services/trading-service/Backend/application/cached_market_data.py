"""
Cached wrapper around market_data_store for performance optimization.

Caches candles with 10s TTL and invalidates on new data arrival.
Expected improvement: 70% reduction in database hits.
"""

from __future__ import annotations

import logging
from typing import Any

from Backend.application.cache_service import get_cache, cache_key
from Backend.application import market_data_store

logger = logging.getLogger("quantgrid.cached_market_data")

CANDLES_TTL = 10
PRICE_TICK_TTL = 5
SUMMARY_TTL = 60


def latest_candles(symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
    """Get latest candles with caching."""
    cache = get_cache()
    key = cache_key("candles", symbol, interval, prefix="market_data")
    
    cached = cache.get(key)
    if cached is not None:
        return cached
    
    candles = market_data_store.latest_candles(symbol, interval, limit)
    cache.set(key, candles, ttl_seconds=CANDLES_TTL)
    
    return candles


def store_candles(
    *,
    symbol: str,
    market_symbol: str,
    interval: str,
    source: str,
    candles: list[dict[str, Any]],
) -> None:
    """Store candles and invalidate cache."""
    market_data_store.store_candles(
        symbol=symbol,
        market_symbol=market_symbol,
        interval=interval,
        source=source,
        candles=candles,
    )
    
    cache = get_cache()
    cache.delete_pattern(f"market_data:candles:{symbol.upper()}:*")
    logger.debug(
        "cache_invalidated",
        extra={"reason": "new_candles", "symbol": symbol},
    )


def latest_price_tick(symbol: str) -> dict[str, Any] | None:
    """Get latest price tick with caching."""
    cache = get_cache()
    key = cache_key("price_tick", symbol, prefix="market_data")
    
    cached = cache.get(key)
    if cached is not None:
        return cached
    
    tick = market_data_store.latest_price_tick(symbol)
    if tick is not None:
        cache.set(key, tick, ttl_seconds=PRICE_TICK_TTL)
    
    return tick


def store_price_tick(payload: dict[str, Any]) -> None:
    """Store price tick and invalidate cache."""
    market_data_store.store_price_tick(payload)
    
    symbol = str(payload.get("symbol") or "").upper()
    if symbol:
        cache = get_cache()
        cache.delete(cache_key("price_tick", symbol, prefix="market_data"))
        logger.debug(
            "cache_invalidated",
            extra={"reason": "new_price_tick", "symbol": symbol},
        )


def market_data_summary(symbol: str, interval: str) -> dict[str, Any]:
    """Get market data summary with caching."""
    cache = get_cache()
    key = cache_key("summary", symbol, interval, prefix="market_data")
    
    cached = cache.get(key)
    if cached is not None:
        return cached
    
    summary = market_data_store.market_data_summary(symbol, interval)
    cache.set(key, summary, ttl_seconds=SUMMARY_TTL)
    
    return summary


def batch_latest_candles(
    symbols: list[str],
    interval: str = "1m",
    limit: int = 100,
) -> dict[str, list[dict[str, Any]]]:
    """Batch fetch candles for multiple symbols."""
    cache = get_cache()
    result = {}
    symbols_to_fetch = []
    
    for symbol in symbols:
        key = cache_key("candles", symbol, interval, prefix="market_data")
        cached = cache.get(key)
        if cached is not None:
            result[symbol] = cached
        else:
            symbols_to_fetch.append(symbol)
    
    if symbols_to_fetch:
        for symbol in symbols_to_fetch:
            candles = market_data_store.latest_candles(symbol, interval, limit)
            key = cache_key("candles", symbol, interval, prefix="market_data")
            cache.set(key, candles, ttl_seconds=CANDLES_TTL)
            result[symbol] = candles
    
    return result


def invalidate_all_candles() -> int:
    """Invalidate all cached candle data."""
    cache = get_cache()
    return cache.delete_pattern("market_data:candles:*")


def invalidate_all_price_ticks() -> int:
    """Invalidate all cached price ticks."""
    cache = get_cache()
    return cache.delete_pattern("market_data:price_tick:*")


def cache_stats() -> dict[str, Any]:
    """Get cache performance statistics."""
    cache = get_cache()
    return cache.stats()
