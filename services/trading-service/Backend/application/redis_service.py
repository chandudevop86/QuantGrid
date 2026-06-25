from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

logger = logging.getLogger("quantgrid.redis")


@dataclass
class RedisStatus:
    healthy: bool
    mode: str
    message: str
    url_configured: bool


class RedisService:
    def __init__(self) -> None:
        self.url = os.getenv("REDIS_URL") or os.getenv("QUANTGRID_REDIS_URL")
        self.client: Any | None = None
        self.async_client: Any | None = None
        self._status = RedisStatus(False, "not_configured", "REDIS_URL is not configured.", False)

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
            self.async_client = async_redis.Redis.from_url(self.url, socket_connect_timeout=0.5, socket_timeout=0.5)
            self._status = RedisStatus(True, "redis", "Redis ping ok.", True)
        except Exception as exc:
            logger.exception("redis_startup_validation_failed", extra={"error_type": exc.__class__.__name__})
            self.client = None
            self.async_client = None
            self._status = RedisStatus(False, "fallback", f"Redis unavailable; using fallback: {exc}", True)
        return self._status

    def status(self) -> dict[str, Any]:
        if self.url and self.client is not None:
            try:
                self.client.ping()
                self._status = RedisStatus(True, "redis", "Redis ping ok.", True)
            except Exception as exc:
                self._status = RedisStatus(False, "fallback", f"Redis ping failed; using fallback: {exc}", True)
        return {
            "healthy": self._status.healthy,
            "mode": self._status.mode,
            "message": self._status.message,
            "url_configured": self._status.url_configured,
        }

    async def publish_json(self, channel: str, payload: dict[str, Any]) -> bool:
        if self.async_client is None:
            return False
        try:
            await self.async_client.publish(channel, json.dumps(payload, default=str))
            return True
        except Exception as exc:
            logger.warning("redis_publish_failed", extra={"channel": channel, "error_type": exc.__class__.__name__})
            return False

    async def subscribe_json(self, channel: str, callback: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        if self.async_client is None:
            return
        pubsub = self.async_client.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    await callback(json.loads(message.get("data")))
                except Exception:
                    logger.exception("redis_subscriber_callback_failed", extra={"channel": channel})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("redis_subscriber_failed", extra={"channel": channel})
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()


redis_service = RedisService()
