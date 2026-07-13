from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from Backend.application.market_data_service import get_market_data_service
from Backend.application.redis_service import redis_service
from Backend.presentation.api.websocket_manager import manager


_task: asyncio.Task | None = None
logger = logging.getLogger("quantgrid.market_stream")


def start_market_data_stream(symbols: list[str] | None = None) -> None:
    global _task
    if _task is not None and not _task.done():
        return
    loop = asyncio.get_running_loop()
    _task = loop.create_task(_market_data_loop(symbols or _configured_symbols()))


async def stop_market_data_stream() -> None:
    global _task
    task = _task
    _task = None
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _market_data_loop(symbols: list[str]) -> None:
    interval = max(1, int(os.getenv("QUANTGRID_MARKET_STREAM_POLL_SECONDS", "3")))
    while True:
        for symbol in symbols:
            try:
                service = get_market_data_service()
                tick = await asyncio.to_thread(service.get_ltp, symbol, mode="paper")
                await publish_tick(tick)
            except Exception as exc:
                logger.warning(
                    "market_stream_fetch_failed",
                    extra={"symbol": symbol.upper(), "error_type": exc.__class__.__name__},
                )
                await manager.broadcast(_feed_down_payload(symbol))
        await asyncio.sleep(interval)


async def publish_tick(tick: dict[str, Any]) -> None:
    await redis_service.publish_json("quantgrid:market:ticks", tick)
    await manager.broadcast({"type": "market_tick", "payload": tick})


def _configured_symbols() -> list[str]:
    raw = os.getenv("QUANTGRID_MARKET_STREAM_SYMBOLS", "NIFTY")
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def _feed_down_payload(symbol: str) -> dict[str, Any]:
    return {
        "type": "market_feed_status",
        "payload": {
            "symbol": symbol.upper(),
            "feed_status": "FEED DOWN",
            "error": "market_data_provider_unavailable",
        },
    }
