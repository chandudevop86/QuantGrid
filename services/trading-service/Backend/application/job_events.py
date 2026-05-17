from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def publish_job_update(job: dict) -> None:
    try:
        import redis
    except ImportError:
        logger.warning("Redis package is not installed; websocket job updates are disabled")
        return

    try:
        client = redis.Redis.from_url(REDIS_URL)
        client.publish("updates", json.dumps(job, default=str))
    except Exception:
        logger.exception("Failed to publish job update to Redis")
