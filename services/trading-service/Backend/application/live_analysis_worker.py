from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel

from Backend.application.dto import serialize_signal
from Backend.application.job_events import publish_job_update
from Backend.application.job_store import claim_job, claim_next_queued_job, update_job, utc_now
from Backend.application.trading_service import TradingService
from Backend.presentation.api.market_api import get_candles

logger = logging.getLogger(__name__)
service = TradingService()


class LiveAnalysisPayload(BaseModel):
    symbol: str
    interval: str = "1m"
    period: str = "1d"
    strategy: str = "breakout"
    capital: float = 100000
    risk_pct: float = 1
    rr_ratio: float = 2


def _prepare_strategy_candles(candles_response: dict[str, Any]) -> list[dict[str, Any]]:
    candles = list(candles_response.get("candles", []))
    if candles_response.get("volume_status") == "not_reported_for_index":
        return [{**candle, "volume": None} for candle in candles]
    return candles


def run_live_analysis(payload: LiveAnalysisPayload) -> dict[str, Any]:
    candles_response = get_candles(
        payload.symbol,
        interval=payload.interval,
        period=payload.period,
    )
    candles = _prepare_strategy_candles(candles_response)
    signals = service.run_strategy(
        strategy_name=payload.strategy,
        data=candles,
        symbol=payload.symbol.upper(),
        capital=payload.capital,
        risk_pct=payload.risk_pct,
        rr_ratio=payload.rr_ratio,
    )
    return {
        "candles_analyzed": len(candles),
        "market_data": {
            "source": candles_response.get("source"),
            "market_symbol": candles_response.get("market_symbol"),
            "volume_status": candles_response.get("volume_status"),
            "warning": candles_response.get("warning"),
        },
        "signals": [serialize_signal(signal) for signal in signals],
    }


def _finish_claimed_job(job_id: str, payload_data: dict[str, Any]) -> dict[str, Any] | None:
    payload = LiveAnalysisPayload(**payload_data)
    try:
        result = run_live_analysis(payload)
        finished_job = update_job(
            job_id,
            {
                "status": "completed",
                "completed_at": utc_now(),
                "result": result,
            },
        )
    except Exception as exc:
        logger.exception("Live analysis job failed: %s", job_id)
        finished_job = update_job(
            job_id,
            {
                "status": "failed",
                "completed_at": utc_now(),
                "error": str(exc),
            },
        )

    if finished_job:
        publish_job_update(finished_job)
    return finished_job


def execute_job(job_id: str) -> dict[str, Any] | None:
    claimed = claim_job(job_id)
    if claimed is None:
        return None

    job, payload_data = claimed
    publish_job_update(job)
    return _finish_claimed_job(job_id, payload_data)


def process_next_job() -> dict[str, Any] | None:
    claimed = claim_next_queued_job()
    if claimed is None:
        return None

    job, payload_data = claimed
    publish_job_update(job)
    return _finish_claimed_job(job["job_id"], payload_data)


def run_worker_loop(poll_interval: float = 1.0) -> None:
    logger.info("Live analysis worker started")
    while True:
        processed = process_next_job()
        if processed is None:
            time.sleep(poll_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker_loop()
