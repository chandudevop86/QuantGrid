from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from Backend.application.candle_validation import validate_live_candle
from Backend.application.decision_pipeline import DecisionPipelineService
from Backend.application.job_queue import enqueue_job
from Backend.application.worker import process_job
from Backend.application.job_store import count_jobs, list_jobs, utc_now
from Backend.application.live_analysis_worker import LiveAnalysisPayload
from Backend.application.market_data_store import latest_candles, market_data_summary
from Backend.application.notifications import alert_job_created
from Backend.application.paper_trade_store import risk_status
from Backend.application.redis_service import redis_service
from Backend.application.monitoring import observe_api_request, observe_market_data_age, observe_risk_block, observe_trading_decision
from Backend.core.config import get_settings
from Backend.core.database import SessionLocal, get_db
from Backend.domain.engine.strategy_engine import StrategyEngine
from Backend.domain.security.audit import list_audit_events, write_audit_log
from Backend.domain.security.models import User
from Backend.presentation.api.auth import current_user
from Backend.presentation.api.roles import require_roles
from Backend.presentation.api.websocket_manager import manager

router = APIRouter()
compatibility_router = APIRouter()
logger = logging.getLogger("quantgrid.dashboard")


def _present_job(job: dict) -> dict:
    if job.get("status") != "queued" or job.get("queued_at"):
        return job

    return {
        **job,
        "status": "stale",
        "note": "This job was queued before durable live-analysis jobs were enabled.",
    }


@router.get("/summary")
def summary(_role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops"))):
    return _product_summary(operations(_role))


def _product_summary(payload: dict) -> dict:
    decision = payload.get("decision") or {}
    factors = decision.get("factor_snapshot") or {}
    final = factors.get("final_decision") or {}
    confidence = final.get("trade_confidence") or {}
    eligibility = final.get("trade_eligibility") or {"eligible": False, "status": "BLOCKED", "reasons": ["Decision eligibility is unavailable."]}
    no_trade = final.get("no_trade_intelligence") or {}
    quality = factors.get("data_quality") or (factors.get("checklist") or {}).get("data_quality") or {}
    market = payload.get("market_status") or {}
    health = payload.get("system_health") or {}
    risk = payload.get("risk_summary") or {}
    return {
        "status": "ready",
        "contract_version": "1.0",
        "updated_at": payload.get("updated_at"),
        "market_decision": {
            "bias": final.get("market_bias") or decision.get("market_bias"),
            "decision": final.get("trade_decision") or decision.get("trade_recommendation"),
            "trade_quality": final.get("trade_quality"),
            "trade_confidence": confidence,
            "system_status": final.get("system_status") or decision.get("system_status"),
        },
        "why_this_decision": {
            "plain_english": (final.get("explainability") or {}).get("plain_english") or decision.get("simple_explanation"),
            "supporting_factors": final.get("supporting_factors") or decision.get("supporting_factors") or [],
            "opposing_factors": final.get("opposing_factors") or decision.get("opposing_factors") or [],
            "warnings": (final.get("explainability") or {}).get("warnings") or decision.get("warnings") or [],
        },
        "trade_or_no_trade": {
            "eligibility": eligibility,
            "trade_plan": final.get("trade_plan") if eligibility.get("eligible") else None,
            "no_trade": no_trade if not eligibility.get("eligible") else None,
        },
        "key_levels": {
            "support": decision.get("support"),
            "resistance": decision.get("resistance"),
            "entry_zone": final.get("entry_zone"),
            "invalidation_level": final.get("invalidation_level") or decision.get("invalidation_level"),
        },
        "system_trust": {
            "market": market,
            "data_quality": quality,
            "api": health.get("api"),
            "database": health.get("db"),
            "market_data": health.get("market_data"),
            "broker": health.get("broker"),
            "worker": health.get("background_worker"),
            "risk_state": risk.get("active_risk_state"),
            "execution_mode": risk.get("execution_mode"),
        },
    }


def _redis_status() -> dict:
    status = redis_service.status()
    return {
        "connected": bool(status["healthy"]),
        "healthy": bool(status["healthy"]),
        "mode": status["mode"],
        "message": status["message"],
        "url_configured": status["url_configured"],
    }


def _worker_status() -> dict:
    heartbeat = redis_service.read_worker_heartbeat()
    active_jobs = count_jobs("running")
    if not heartbeat:
        return {
            "healthy": False,
            "status": "UNKNOWN",
            "active_jobs": active_jobs,
            "last_seen": None,
            "worker_id": None,
            "message": "Worker heartbeat is unavailable; job counts do not prove worker health.",
        }
    return {
        "healthy": True,
        "status": "RUNNING",
        "active_jobs": active_jobs,
        "last_seen": heartbeat.get("last_seen"),
        "worker_id": heartbeat.get("worker_id"),
        "message": "Worker heartbeat received through Redis.",
    }


def _float_env(name: str) -> float | None:
    raw = os.getenv(name)
    if raw in {None, ""}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _bool_env(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _timestamp_bucket(candle: dict, interval_seconds: int) -> int | None:
    raw = candle.get("timestamp") or candle.get("datetime") or candle.get("time")
    if raw in {None, ""}:
        return None
    try:
        value = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    timestamp = value.timestamp() if value.tzinfo is not None else value.replace(tzinfo=timezone.utc).timestamp()
    return int(timestamp // interval_seconds * interval_seconds)


def _aggregate_candles(candles: list[dict], interval_seconds: int, limit: int = 100) -> list[dict]:
    buckets: dict[int, list[dict]] = {}
    for candle in candles:
        bucket = _timestamp_bucket(candle, interval_seconds)
        if bucket is None:
            continue
        buckets.setdefault(bucket, []).append(candle)

    aggregated = []
    for bucket, rows in sorted(buckets.items()):
        if not rows:
            continue
        opens = [row.get("open") for row in rows if row.get("open") is not None]
        highs = [row.get("high") for row in rows if row.get("high") is not None]
        lows = [row.get("low") for row in rows if row.get("low") is not None]
        closes = [row.get("close") for row in rows if row.get("close") is not None]
        if not opens or not highs or not lows or not closes:
            continue
        aggregated.append({
            "timestamp": datetime.fromtimestamp(bucket, timezone.utc).isoformat(),
            "open": float(opens[0]),
            "high": max(float(value) for value in highs),
            "low": min(float(value) for value in lows),
            "close": float(closes[-1]),
            "volume": sum(float(row.get("volume") or 0) for row in rows),
            "source": "derived-from-stored-candles",
        })
    return aggregated[-limit:]


def _dashboard_candles_by_interval(symbol: str) -> dict[str, list[dict]]:
    one_minute = latest_candles(symbol, "1m", 300)
    five_minute = latest_candles(symbol, "5m", 100) or _aggregate_candles(one_minute, 300)
    fifteen_minute = latest_candles(symbol, "15m", 100) or _aggregate_candles(one_minute, 900)
    one_hour = latest_candles(symbol, "1h", 100) or _aggregate_candles(fifteen_minute or one_minute, 3600)
    return {
        "1m": one_minute[-100:],
        "5m": five_minute,
        "15m": fifteen_minute,
        "1h": one_hour,
        "1d": latest_candles(symbol, "1d", 100),
    }


@router.get("/operations")
def operations(_role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops"))):
    started_at = perf_counter()
    settings = get_settings()
    candles_by_interval = _dashboard_candles_by_interval("NIFTY")
    candles = candles_by_interval["1m"]
    from Backend.presentation.api.market_api import latest_verified_option_context

    market_context = latest_verified_option_context("NIFTY")
    validation = validate_live_candle(candles, interval="1m", mode="paper", source="stored-live-cache")
    observe_market_data_age("NIFTY", "1m", validation.delay_seconds)
    market_store = market_data_summary("NIFTY", "1m")
    risk = risk_status()
    daily_loss_remaining = max(0.0, float(risk["max_daily_loss"]) + float(risk["daily_pnl"]))
    redis = _redis_status()
    strategies = StrategyEngine().available()

    db = None
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db_status = {"healthy": True, "message": "Database query ok."}
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.exception("dashboard_database_health_check_failed", extra={"error_type": exc.__class__.__name__})
        db_status = {
            "healthy": False,
            "status": "UNAVAILABLE",
            "message": "Database health check failed. Review server logs using the request timestamp.",
        }
    finally:
        if db is not None:
            db.close()

    execution_mode = "LIVE" if settings.live_trading_enabled else "PAPER"
    risk_blocked = (
        risk["trades_today"] >= risk["max_trades_per_day"]
        or risk["consecutive_losses"] >= risk["max_consecutive_losses"]
        or daily_loss_remaining <= 0
    )

    trader_message = (
        "Market data is fresh enough for confirmation checks."
        if validation.valid_for_execution
        else "Current market conditions do not meet confirmation criteria."
    )
    pipeline = DecisionPipelineService()
    pipeline_result = pipeline.run(
        pipeline.from_environment(
            validation=validation,
            candles=candles,
            candles_by_interval=candles_by_interval,
            market_context=market_context,
            enforce_data_quality=True,
            symbol="NIFTY",
        ),
        risk_blocked=risk_blocked,
        confidence_threshold=_int_env("CONFIDENCE_THRESHOLD", 70),
    )
    decision = pipeline_result.decision
    latency_ms = round((perf_counter() - started_at) * 1000, 2)
    observe_api_request("GET", "/dashboard/operations", 200, latency_ms / 1000)
    observe_trading_decision(decision.trade_recommendation, decision.data_status, decision.blocked)
    if risk_blocked:
        observe_risk_block("DASHBOARD_RISK_BLOCKED")
    logger.info(
        "dashboard_decision",
        extra={
            "market_bias": decision.market_bias,
            "recommendation": decision.trade_recommendation,
            "confidence": decision.confidence,
            "data_status": decision.data_status,
            "blocked": decision.blocked,
        },
    )

    return {
        "updated_at": utc_now(),
        "decision": decision.to_dict() | {
            "decision_id": pipeline_result.decision_id,
            "factor_snapshot": pipeline_result.factors,
            "recommendation_metrics": pipeline_result.analytics,
        },
        "market_status": {
            "label": validation.ui_status,
            "state": validation.market_status,
            "feed_delay_seconds": validation.delay_seconds,
            "last_candle_timestamp": validation.latest_candle,
            "last_candle_timestamp_ist": validation.latest_candle_ist,
            "session_state": "open" if validation.market_live else "closed",
            "valid_for_execution": validation.valid_for_execution,
            "warnings": validation.warnings,
        },
        "system_health": {
            "api": {"healthy": True, "message": "API ready."},
            "redis": redis,
            "db": db_status,
            "websocket": {
                "active": len(manager.active_connections) > 0,
                "connections": len(manager.active_connections),
            },
            "broker": {
                "configured": settings.broker_configured,
                "connected": False,
                "session_verified": False,
                "provider": settings.broker_provider or "paper",
                "message": (
                    "Broker credentials configured; session not verified by this dashboard check."
                    if settings.broker_configured
                    else "Real-money broker is not configured."
                ),
            },
            "background_worker": _worker_status(),
            "market_data": {
                "healthy": market_store["candles"] > 0,
                "candles": market_store["candles"],
                "latest_timestamp": market_store["latest_candle_at"],
            },
            "strategy_engine": {
                "healthy": {"breakout", "mean_reversion", "supply_demand", "mtf", "btst", "cbt", "crt_tbs", "mtfa"}.issubset(set(strategies)),
                "registered": strategies,
            },
        },
        "risk_summary": {
            **risk,
            "execution_mode": execution_mode,
            "daily_loss_remaining": round(daily_loss_remaining, 2),
            "active_risk_state": "BLOCKED" if risk_blocked else "NORMAL",
            "live_trading_enabled": settings.live_trading_enabled,
            "risk_configured": settings.risk_configured,
        },
        "observability": {
            "websocket_connections": len(manager.active_connections),
            "api_latency_ms": latency_ms,
            "api_latency_status": "OK" if latency_ms < 500 else "SLOW",
            "signal_generation_metrics": None,
            "strategy_execution_metrics": None,
            "signal_count_metrics": None,
            "failed_strategy_execution_metrics": None,
            "option_chain_failure_metrics": None,
            "rejected_order_metrics": None,
            "rejected_order_count": None,
            "feed_delay_seconds": validation.delay_seconds,
            "redis_healthy": redis["connected"],
            "db_healthy": db_status["healthy"],
            "stored_live_candles": market_store["candles"],
            "decision_metrics": pipeline_result.analytics,
        },
        "diagnostics": {
            "trader_message": trader_message,
            "validation_summary": "Execution checks are preserved; advanced validator details are available in developer mode.",
            "technical_details": {
                "warnings": validation.warnings,
                "market_validation": validation.model_dump() if hasattr(validation, "model_dump") else validation.__dict__,
                "risk": risk,
            },
        },
        "backtest_context": {
            "historical_win_rate": None,
            "sharpe_ratio": None,
            "recent_trade_outcomes": [],
            "replay_links": [],
            "message": "Run a backtest or replay to attach historical confidence to this strategy.",
        },
    }


@compatibility_router.get("/operations/status")
def operations_status_alias(_role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops"))):
    return operations(_role)


@router.post("/live-analysis/jobs")
def create_live_analysis_job(
    payload: LiveAnalysisPayload,
    request: Request,
    _role: str = Depends(require_roles("admin", "trader", "analyst")),
    actor: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    metadata = {
        "symbol": payload.symbol.upper(),
        "strategy": payload.strategy,
        "interval": payload.interval,
        "period": payload.period,
    }
    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    created = enqueue_job("live-analysis", payload_data, metadata=metadata, job_id=str(uuid4()))
    write_audit_log(
        db,
        action="trading_job_created",
        actor=actor,
        target_type="job",
        target_id=created["job_id"],
        request=request,
        metadata={"symbol": metadata["symbol"], "strategy": metadata["strategy"], "status": "queued"},
    )
    alert_job_created(created)
    processed = process_job(created["job_id"])
    return processed if processed and processed.get("job_id") == created["job_id"] else created


@router.get("/live-analysis/jobs")
def list_live_analysis_jobs(_role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops"))):
    return {"jobs": [_present_job(job) for job in list_jobs()]}


@router.get("/audit-trail")
def audit_trail(
    limit: int = 50,
    _role: str = Depends(require_roles("admin", "developer", "ops")),
    db: Session = Depends(get_db),
):
    return {"events": list_audit_events(db, limit)}
