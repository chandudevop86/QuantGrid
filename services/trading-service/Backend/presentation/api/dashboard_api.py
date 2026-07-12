from __future__ import annotations

import os
import logging
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
    return {
        "status": "ready",
        "open_positions": 0,
        "active_jobs": count_jobs("running"),
        "total_jobs": count_jobs(),
        "updated_at": utc_now(),
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


@router.get("/operations")
def operations(_role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops"))):
    started_at = perf_counter()
    settings = get_settings()
    candles = latest_candles("NIFTY", "1m", 100)
    candles_by_interval = {
        "1m": candles,
        "5m": latest_candles("NIFTY", "5m", 100),
        "15m": latest_candles("NIFTY", "15m", 100),
        "1h": latest_candles("NIFTY", "1h", 100),
        "1d": latest_candles("NIFTY", "1d", 100),
    }
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
            "background_worker": {
                "healthy": False,
                "status": "UNKNOWN",
                "active_jobs": count_jobs("running"),
                "message": "Worker heartbeat is not available; job counts do not prove worker health.",
            },
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
