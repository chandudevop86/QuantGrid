from __future__ import annotations

import json
import logging
import asyncio

from Backend.application.redis_service import redis_service
from Backend.presentation.api.websocket_manager import manager

logger = logging.getLogger(__name__)


def publish_job_update(job: dict) -> None:
    if manager.loop:
        asyncio.run_coroutine_threadsafe(manager.broadcast(job), manager.loop)
        asyncio.run_coroutine_threadsafe(redis_service.publish_json("updates", json.loads(json.dumps(job, default=str))), manager.loop)
