from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel

from Backend.application.candle_validation import validate_live_candle
from Backend.application.dto import serialize_signal
from Backend.application.job_events import publish_job_update
from Backend.application.job_store import claim_job, claim_next_queued_job, update_job, utc_now
from Backend.application.notifications import alert_job_finished
from Backend.application.paper_trade_store import create_paper_trade
from Backend.application.signal_validation import validate_signals
from Backend.application.signal_quality import split_signals
from Backend.domain.engine.execution_engine import ExecutionEngine
from Backend.domain.execution_constraints import apply_order_constraints, requested_quantity, validate_execution_constraints
from Backend.domain.models.order import Order
from Backend.domain.models.signal import StrategySignal
from Backend.domain.market_structure import analyze_market_structure
from Backend.application.trading_service import TradingService
from Backend.presentation.api.market_api import get_candles

logger = logging.getLogger(__name__)
JOB_START_DELAY_SECONDS = 0.75


class LiveAnalysisPayload(BaseModel):
    symbol: str
    interval: str = "1m"
    period: str = "1d"
    strategy: str = "breakout"
    capital: float = 100000
    risk_pct: float = 1
    rr_ratio: float = 2
    auto_trade: bool = False
    execution_mode: str = "paper"


def _serialize_order(order: Order) -> dict[str, Any]:
    serialized = asdict(order)
    if order.created_at is not None:
        serialized["created_at"] = order.created_at.isoformat()
    return serialized


def _generate_paper_trades(signals: list[StrategySignal]) -> list[dict[str, Any]]:
    execution_engine = ExecutionEngine()
    trades: list[dict[str, Any]] = []
    for signal in signals:
        constraints = validate_execution_constraints(signal)
        if not constraints.accepted:
            trades.append({
                "status": "no_trade",
                "source": "auto_signal",
                "reason": constraints.reason,
                "lot_size": constraints.lot_size,
                "rounded_quantity": constraints.quantity,
                "required_margin": constraints.required_margin,
            })
            continue

        order = apply_order_constraints(
            execution_engine.order_from_signal(signal),
            constraints,
            requested_quantity(signal),
        )
        trades.append({
            "status": "paper_simulated",
            "source": "auto_signal",
            "order": _serialize_order(order),
        })
        create_paper_trade(
            {
                "strategy": signal.strategy_name,
                "symbol": signal.symbol,
                "side": signal.side,
                "entry": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "target": signal.target_price,
                "status": "paper_simulated",
                "pnl": 0.0,
                "reason": "OK",
                "score": signal.metadata.get("score") or signal.metadata.get("total_score") or 0,
                "regime": signal.metadata.get("regime"),
                "signal_time": signal.signal_time.isoformat(),
            }
        )
    return trades


def _prepare_strategy_candles(candles_response: dict[str, Any]) -> list[dict[str, Any]]:
    candles = list(candles_response.get("candles", []))
    if candles_response.get("volume_status") == "not_reported_for_index":
        return [{**candle, "volume": None} for candle in candles]
    return candles


def run_live_analysis(payload: LiveAnalysisPayload) -> dict[str, Any]:
    execution_mode = payload.execution_mode.strip().lower()
    if execution_mode != "paper":
        raise ValueError("Live auto-trading is disabled; only paper execution is supported.")

    candles_response = get_candles(payload.symbol, interval=payload.interval, period=payload.period)
    confirmation_response = get_candles(payload.symbol, interval="5m", period=payload.period)
    trend_response = get_candles(payload.symbol, interval="15m", period=payload.period)
    candles = _prepare_strategy_candles(candles_response)
    confirmation_candles = _prepare_strategy_candles(confirmation_response)
    trend_candles = _prepare_strategy_candles(trend_response)
    service = TradingService()
    candle_validation = validate_live_candle(
        candles,
        interval=payload.interval,
        mode="paper",
        source=candles_response.get("source"),
        provider_fetched_at=candles_response.get("fetched_at"),
    )
    raw_signals = service.run_strategy(
        strategy_name=payload.strategy,
        data=candles,
        symbol=payload.symbol.upper(),
        capital=payload.capital,
        risk_pct=payload.risk_pct,
        rr_ratio=payload.rr_ratio,
        params={"mtf_candles": confirmation_candles, "htf_candles": trend_candles},
    )
    gate_active_signals, rejected_signals, stale_signals = split_signals(
        raw_signals,
        candles_1m=candles,
        candles_15m=trend_candles,
    )
    signals, data_source = validate_signals(
        gate_active_signals,
        symbol=payload.symbol,
        candles=candles,
        candle_source=candles_response.get("source"),
    )
    serialized_signals = [serialize_signal(signal) for signal in signals]
    institutional_analysis = analyze_market_structure(candles, signals=signals, raw_signals=raw_signals)
    auto_trades = _generate_paper_trades(signals) if payload.auto_trade else []
    logger.info(
        "Live analysis generated %s signals and %s trades for %s/%s",
        len(serialized_signals),
        len(auto_trades),
        payload.symbol.upper(),
        payload.strategy,
    )
    return {
        "data_source": data_source,
        "candles_analyzed": len(candles),
        "auto_trade": payload.auto_trade,
        "execution_mode": execution_mode,
        "market_data": {
            "source": candles_response.get("source"),
            "market_symbol": candles_response.get("market_symbol"),
            "volume_status": candles_response.get("volume_status"),
            "warning": candles_response.get("warning"),
            "validation": candle_validation.model_dump(),
        },
        "validation": candle_validation.model_dump(),
        "institutional_analysis": institutional_analysis,
        "signals": serialized_signals,
        "active_signals": serialized_signals,
        "rejected_signals": [
            {"signal": serialize_signal(item["signal"]), "decision": item["decision"]}
            for item in rejected_signals
        ],
        "stale_signals": [
            {"signal": serialize_signal(item["signal"]), "decision": item["decision"]}
            for item in stale_signals
        ],
        "trades": auto_trades,
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
        alert_job_finished(finished_job)
    return finished_job


async def execute_job(job_id: str) -> dict[str, Any] | None:
    await asyncio.sleep(JOB_START_DELAY_SECONDS)
    claimed = claim_job(job_id)
    if claimed is None:
        return None

    job, payload_data = claimed
    publish_job_update(job)
    await asyncio.sleep(JOB_START_DELAY_SECONDS)
    return await asyncio.to_thread(_finish_claimed_job, job_id, payload_data)


def process_next_job() -> dict[str, Any] | None:
    time.sleep(JOB_START_DELAY_SECONDS)
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
