from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from Backend.application.candle_validation import validate_live_candle
from Backend.application.job_queue import enqueue_job
from Backend.application.job_store import count_jobs, list_jobs, utc_now
from Backend.application.live_analysis_worker import LiveAnalysisPayload
from Backend.application.market_data_store import latest_candles, market_data_summary
from Backend.application.notifications import alert_job_created
from Backend.application.paper_trade_store import risk_status
from Backend.application.redis_service import redis_service
from Backend.application.monitoring import observe_market_data_age
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


@router.get("/operations")
def operations(_role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops"))):
    settings = get_settings()
    candles = latest_candles("NIFTY", "1m", 100)
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
        db_status = {"healthy": False, "message": str(exc)}
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

    return {
        "updated_at": utc_now(),
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
                "connected": settings.broker_configured,
                "provider": settings.broker_provider or "paper",
                "message": "Broker configured." if settings.broker_configured else "Real-money broker disconnected.",
            },
            "background_worker": {
                "healthy": count_jobs("running") >= 0,
                "active_jobs": count_jobs("running"),
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
            "api_latency_ms": 0,
            "api_latency_status": 0,
            "signal_generation_metrics": {"generated": 0, "validated": 0},
            "strategy_execution_metrics": 0,
            "signal_count_metrics": 0,
            "failed_strategy_execution_metrics": 0,
            "option_chain_failure_metrics": 0,
            "rejected_order_metrics": 0,
            "rejected_order_count": 0,
            "feed_delay_seconds": validation.delay_seconds,
            "redis_healthy": redis["connected"],
            "db_healthy": db_status["healthy"],
            "stored_live_candles": market_store["candles"],
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
            "historical_win_rate": 0.0,
            "sharpe_ratio": 0.0,
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
    return created


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
