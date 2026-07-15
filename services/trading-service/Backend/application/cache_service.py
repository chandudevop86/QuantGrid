"""
Multi-level caching service: Redis + in-process cache with TTL.

Provides deterministic, configurable caching for market data, strategy registry,
and other high-frequency queries.

Usage:
    # Cache market candles (read-heavy)
    cache.set("candles:NIFTY:1m", candles, ttl_seconds=10)
    cached = cache.get("candles:NIFTY:1m")
    
    # Invalidate on data change
    cache.delete("candles:NIFTY:1m")
    cache.delete_pattern("candles:NIFTY:*")
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, TypeVar, Generic

logger = logging.getLogger("quantgrid.cache")

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """In-process cache entry with TTL."""
    value: T
    expires_at: float
    hits: int = 0
    
    def is_expired(self, now: float) -> bool:
        return now > self.expires_at


class MultiLevelCache:
    """
    Redis-backed cache with in-process fallback.
    
    - Reads: Redis → in-process cache → compute
    - Writes: Redis + in-process cache
    - Eviction: Auto-expire on TTL
    """
    
    def __init__(self, redis_service: Any = None) -> None:
        self.redis_service = redis_service
        self._local_cache: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._max_local_entries = 1000
        self._stats = {
            "redis_hits": 0,
            "local_hits": 0,
            "misses": 0,
            "redis_failures": 0,
            "evictions": 0,
        }
    
    def get(self, key: str) -> Any | None:
        """Read from Redis → in-process → None."""
        now = time.time()
        
        # Try in-process cache first (fastest)
        with self._lock:
            entry = self._local_cache.get(key)
            if entry is not None and not entry.is_expired(now):
                entry.hits += 1
                self._stats["local_hits"] += 1
                return entry.value
            # Clean expired entry
            if entry is not None and entry.is_expired(now):
                del self._local_cache[key]
        
        # Try Redis (if configured)
        if self.redis_service and self.redis_service.client:
            try:
                value = self.redis_service.get_json(key)
                if value is not None:
                    self._stats["redis_hits"] += 1
                    # Populate local cache
                    with self._lock:
                        self._local_cache[key] = CacheEntry(
                            value=value,
                            expires_at=now + 60,  # Local TTL: 60s
                        )
                    return value
            except Exception as exc:
                logger.warning(
                    "cache_redis_read_failed",
                    extra={"key": key, "error": str(exc)},
                )
                self._stats["redis_failures"] += 1
        
        self._stats["misses"] += 1
        return None
    
    def set(self, key: str, value: Any, *, ttl_seconds: int = 60) -> bool:
        """Write to Redis + in-process cache."""
        success = True
        now = time.time()
        ttl_seconds = max(1, int(ttl_seconds))
        
        # Set in-process cache
        with self._lock:
            self._local_cache[key] = CacheEntry(
                value=value,
                expires_at=now + ttl_seconds,
            )
            # Evict oldest entries if cache is full
            if len(self._local_cache) > self._max_local_entries:
                self._evict_lru()
        
        # Set in Redis
        if self.redis_service and self.redis_service.client:
            try:
                self.redis_service.set_json(key, value, ttl_seconds=ttl_seconds)
            except Exception as exc:
                logger.warning(
                    "cache_redis_write_failed",
                    extra={"key": key, "error": str(exc)},
                )
                success = False
        
        return success
    
    def delete(self, key: str) -> bool:
        """Remove from both Redis and in-process cache."""
        success = True
        
        # Delete from in-process cache
        with self._lock:
            self._local_cache.pop(key, None)
        
        # Delete from Redis
        if self.redis_service and self.redis_service.client:
            try:
                self.redis_service.client.delete(key)
            except Exception as exc:
                logger.warning(
                    "cache_redis_delete_failed",
                    extra={"key": key, "error": str(exc)},
                )
                success = False
        
        return success
    
    def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching a pattern (e.g., 'candles:NIFTY:*')."""
        count = 0
        
        # Delete from in-process cache
        with self._lock:
            keys_to_delete = [k for k in self._local_cache.keys() if self._matches_pattern(k, pattern)]
            for key in keys_to_delete:
                del self._local_cache[key]
                count += 1
        
        # Delete from Redis
        if self.redis_service and self.redis_service.client:
            try:
                cursor = 0
                while True:
                    cursor, keys = self.redis_service.client.scan(
                        cursor=cursor,
                        match=pattern,
                        count=100,
                    )
                    if keys:
                        self.redis_service.client.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break
            except Exception as exc:
                logger.warning(
                    "cache_redis_pattern_delete_failed",
                    extra={"pattern": pattern, "error": str(exc)},
                )
        
        return count
    
    @staticmethod
    def _matches_pattern(key: str, pattern: str) -> bool:
        """Simple glob matching: 'candles:NIFTY:*' matches 'candles:NIFTY:1m'."""
        if "*" not in pattern:
            return key == pattern
        parts = pattern.split("*")
        if not key.startswith(parts[0]):
            return False
        if len(parts) == 1:
            return True
        if len(parts) == 2:
            return key.endswith(parts[1]) or parts[1] == ""
        # Multi-wildcard: simple scan
        idx = 0
        for part in parts:
            if not part:
                continue
            pos = key.find(part, idx)
            if pos == -1:
                return False
            idx = pos + len(part)
        return True
    
    def clear(self) -> None:
        """Clear all local cache entries."""
        with self._lock:
            self._local_cache.clear()
    
    def stats(self) -> dict[str, Any]:
        """Cache performance statistics."""
        total = sum(
            self._stats[k]
            for k in ["redis_hits", "local_hits", "misses"]
        )
        hit_rate = (
            (self._stats["redis_hits"] + self._stats["local_hits"]) / total * 100
            if total > 0
            else 0
        )
        with self._lock:
            local_size = len(self._local_cache)
        
        return {
            "local_entries": local_size,
            "redis_hits": self._stats["redis_hits"],
            "local_hits": self._stats["local_hits"],
            "misses": self._stats["misses"],
            "hit_rate_pct": round(hit_rate, 2),
            "redis_failures": self._stats["redis_failures"],
            "evictions": self._stats["evictions"],
        }
    
    def _evict_lru(self) -> None:
        """Evict least-recently-used entry (by hits)."""
        if not self._local_cache:
            return
        
        lru_key = min(
            self._local_cache.keys(),
            key=lambda k: (self._local_cache[k].hits, time.time() - self._local_cache[k].expires_at),
        )
        del self._local_cache[lru_key]
        self._stats["evictions"] += 1


def cache_key(*parts: str, prefix: str = "") -> str:
    """Generate deterministic cache key.
    
    Example:
        cache_key("candles", "NIFTY", "1m", prefix="market_data")
        → "market_data:candles:NIFTY:1m"
    """
    full_key = ":".join(str(p).upper() for p in parts)
    if prefix:
        return f"{prefix}:{full_key}"
    return full_key


def cache_key_hash(*parts: str, prefix: str = "") -> str:
    """Generate cache key with SHA256 hash (for large composite keys).
    
    Use when composite key > 100 chars or contains special characters.
    """
    composite = ":".join(str(p) for p in parts)
    hash_val = hashlib.sha256(composite.encode()).hexdigest()[:16]
    if prefix:
        return f"{prefix}:{hash_val}"
    return hash_val


_cache_instance: MultiLevelCache | None = None


def get_cache() -> MultiLevelCache:
    """Get or create cache instance."""
    global _cache_instance
    if _cache_instance is None:
        from Backend.application.redis_service import redis_service
        _cache_instance = MultiLevelCache(redis_service)
    return _cache_instance


def init_cache(redis_service: Any | None = None) -> MultiLevelCache:
    """Initialize cache with Redis service."""
    global _cache_instance
    _cache_instance = MultiLevelCache(redis_service)
    return _cache_instance
