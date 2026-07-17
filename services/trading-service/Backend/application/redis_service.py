from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import threading
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable, Awaitable

logger = logging.getLogger("quantgrid.redis")


@dataclass
class RedisStatus:
    healthy: bool
    mode: str
    message: str
    url_configured: bool


class RedisService:
    WORKER_HEARTBEAT_KEY = "quantgrid:worker:heartbeat"
    COOLDOWN_KEY_PREFIX = "quantgrid:cooldown:"
    LOCK_KEY_PREFIX = "quantgrid:lock:"
    def __init__(self) -> None:
        self.url = os.getenv("REDIS_URL") or os.getenv("QUANTGRID_REDIS_URL")
        self.client: Any | None = None
        self.async_client: Any | None = None
        self._status = RedisStatus(False, "not_configured", "REDIS_URL is not configured.", False)
        self._reconnect_lock = threading.Lock()
        self._next_reconnect_at = 0.0

    def configure(self) -> RedisStatus:
        self.url = os.getenv("REDIS_URL") or os.getenv("QUANTGRID_REDIS_URL")
        if not self.url:
            self.client = None
            self.async_client = None
            self._status = RedisStatus(False, "fallback", "Redis unavailable; using in-process fallback.", False)
            return self._status
        try:
            import redis
            import redis.asyncio as async_redis

            self.client = redis.Redis.from_url(self.url, socket_connect_timeout=0.5, socket_timeout=0.5)
            self.client.ping()
            self.async_client = async_redis.Redis.from_url(self.url, socket_connect_timeout=2, socket_timeout=None,
    health_check_interval=40)
            self._status = RedisStatus(True, "redis", "Redis ping ok.", True)
            self._next_reconnect_at = 0.0
        except Exception as exc:
            logger.exception("redis_startup_validation_failed", extra={"error_type": exc.__class__.__name__})
            self._mark_connection_failed("Redis unavailable; using in-process fallback.")
        return self._status

    def _mark_connection_failed(self, message: str = "Redis operation failed; using in-process fallback.") -> None:
        self.client = None
        self.async_client = None
        self._status = RedisStatus(False, "fallback", message, bool(self.url))
        self._next_reconnect_at = monotonic() + self._reconnect_interval_seconds()

    def _reconnect_interval_seconds(self) -> float:
        try:
            return max(1.0, float(os.getenv("QUANTGRID_REDIS_RECONNECT_SECONDS", "10")))
        except (TypeError, ValueError):
            return 10.0

    def _ensure_connected(self) -> bool:
        if self.client is not None:
            return True
        self.url = os.getenv("REDIS_URL") or os.getenv("QUANTGRID_REDIS_URL") or self.url
        if not self.url or monotonic() < self._next_reconnect_at:
            return False
        with self._reconnect_lock:
            if self.client is not None:
                return True
            if monotonic() < self._next_reconnect_at:
                return False
            self._next_reconnect_at = monotonic() + self._reconnect_interval_seconds()
            return self.configure().healthy

    def status(self) -> dict[str, Any]:
        self._ensure_connected()
        if self.url and self.client is not None:
            try:
                self.client.ping()
                self._status = RedisStatus(True, "redis", "Redis ping ok.", True)
            except Exception as exc:
                logger.warning("redis_health_ping_failed", extra={"error_type": exc.__class__.__name__})
                self._mark_connection_failed("Redis health check failed; using in-process fallback.")
        return {
            "healthy": self._status.healthy,
            "mode": self._status.mode,
            "message": self._status.message,
            "url_configured": self._status.url_configured,
        }

    async def publish_json(self, channel: str, payload: dict[str, Any]) -> bool:
        if not self._ensure_connected() or self.async_client is None:
            return False
        try:
            await self.async_client.publish(channel, json.dumps(payload, default=str))
            return True
        except Exception as exc:
            logger.warning("redis_publish_failed", extra={"channel": channel, "error_type": exc.__class__.__name__})
            self._mark_connection_failed()
            return False

    def get_json(self, key: str) -> Any | None:
        if not self._ensure_connected() or self.client is None:
            return None
        try:
            value = self.client.get(key)
            if value is None:
                return None
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            return json.loads(value)
        except Exception as exc:
            logger.warning("redis_json_read_failed", extra={"error_type": exc.__class__.__name__})
            self._mark_connection_failed()
            return None

    def set_json(self, key: str, payload: Any, *, ttl_seconds: int) -> bool:
        if not self._ensure_connected() or self.client is None:
            return False
        try:
            self.client.set(key, json.dumps(payload, default=str), ex=max(1, int(ttl_seconds)))
            return True
        except Exception as exc:
            logger.warning("redis_json_write_failed", extra={"error_type": exc.__class__.__name__})
            self._mark_connection_failed()
            return False

    def write_worker_heartbeat(self, payload: dict[str, Any], *, ttl_seconds: int = 15) -> bool:
        if not self._ensure_connected() or self.client is None:
            return False
        try:
            self.client.set(self.WORKER_HEARTBEAT_KEY, json.dumps(payload, default=str), ex=max(1, ttl_seconds))
            return True
        except Exception as exc:
            logger.warning("redis_worker_heartbeat_write_failed", extra={"error_type": exc.__class__.__name__})
            self._mark_connection_failed()
            return False

    def read_worker_heartbeat(self) -> dict[str, Any] | None:
        if not self._ensure_connected() or self.client is None:
            return None
        try:
            value = self.client.get(self.WORKER_HEARTBEAT_KEY)
            if value is None:
                return None
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            payload = json.loads(value)
            return payload if isinstance(payload, dict) else None
        except Exception as exc:
            logger.warning("redis_worker_heartbeat_read_failed", extra={"error_type": exc.__class__.__name__})
            self._mark_connection_failed()
            return None

    def start_cooldown(self, name: str, *, ttl_seconds: int) -> bool:
        if not self._ensure_connected() or self.client is None:
            return False
        try:
            self.client.set(
                f"{self.COOLDOWN_KEY_PREFIX}{name}",
                "1",
                ex=max(1, int(ttl_seconds)),
            )
            return True
        except Exception as exc:
            logger.warning("redis_cooldown_write_failed", extra={"name": name, "error_type": exc.__class__.__name__})
            self._mark_connection_failed()
            return False

    def cooldown_remaining(self, name: str) -> int | None:
        if not self._ensure_connected() or self.client is None:
            return None
        try:
            ttl = int(self.client.ttl(f"{self.COOLDOWN_KEY_PREFIX}{name}"))
            return ttl if ttl > 0 else None
        except Exception as exc:
            logger.warning("redis_cooldown_read_failed", extra={"name": name, "error_type": exc.__class__.__name__})
            self._mark_connection_failed()
            return None

    def acquire_lock(self, name: str, *, ttl_seconds: int) -> str | None:
        """Return an ownership token, an empty string when busy, or None without Redis."""
        if not self._ensure_connected() or self.client is None:
            return None
        token = secrets.token_urlsafe(24)
        try:
            acquired = self.client.set(
                f"{self.LOCK_KEY_PREFIX}{name}",
                token,
                ex=max(1, int(ttl_seconds)),
                nx=True,
            )
            return token if acquired else ""
        except Exception as exc:
            logger.warning("redis_lock_acquire_failed", extra={"name": name, "error_type": exc.__class__.__name__})
            self._mark_connection_failed()
            return None

    def release_lock(self, name: str, token: str) -> bool:
        if self.client is None or not token:
            return False
        script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
        try:
            return bool(self.client.eval(script, 1, f"{self.LOCK_KEY_PREFIX}{name}", token))
        except Exception as exc:
            logger.warning("redis_lock_release_failed", extra={"name": name, "error_type": exc.__class__.__name__})
            self._mark_connection_failed()
            return False
    async def subscribe_json(
        self,
        channel: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        while True:
            if not self._ensure_connected() or self.async_client is None:
                await asyncio.sleep(self._reconnect_interval_seconds())
                continue

            pubsub = self.async_client.pubsub()

            try:
                await pubsub.subscribe(channel)

                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue

                    try:
                        data = message.get("data")

                        if isinstance(data, bytes):
                            data = data.decode("utf-8")

                        await callback(json.loads(data))

                    except Exception:
                        logger.exception(
                            "redis_subscriber_callback_failed",
                            extra={"channel": channel},
                        )

            except Exception as exc:
                logger.warning(
                    "redis_subscriber_failed",
                    extra={
                        "channel": channel,
                        "error_type": exc.__class__.__name__,
                    },
                )
                self._mark_connection_failed()

            finally:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.close()
                except Exception:
                    logger.warning(
                        "redis_subscriber_cleanup_failed",
                        extra={"channel": channel},
                    )

            await asyncio.sleep(
                self._reconnect_interval_seconds()
            )
redis_service = RedisService()
