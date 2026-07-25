"""Simplified QuantGrid trading execution router.

The module keeps the important behavior from the original implementation:
- subscription and role checks
- paper/live mode separation
- signal shape, market, TQE, risk, and execution-constraint checks
- live HTTPS, feature-flag, broker, kill-switch, and stop-protection guardrails
- duplicate-order suppression and lifecycle tracking
- broker submission and confirmation
- trade/position persistence, auditing, monitoring, and notifications
- auto-paper scan, queued jobs, baskets, scaling, and dashboard endpoints
"""

from __future__ import annotations

import os
from typing import Any, Final, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from Backend.application.broker_circuit_breaker import (
    broker_circuit_status,
    record_broker_failure,
)
from Backend.application.candle_validation import validate_live_candle
from Backend.application.dto import serialize_signal
from Backend.application.job_queue import enqueue_job
from Backend.application.kill_switch import kill_switch_status
from Backend.application.market_data_service import MarketDataService
from Backend.application.market_data_store import latest_candles
from Backend.application.monitoring import (
    observe_paper_order,
    observe_rejected_order,
    observe_signal_generation,
)
from Backend.application.notifications import alert_execution_event
from Backend.application.order_management import OrderManagementService
from Backend.application.order_store import (
    broker_status_to_order_status,
    create_order,
    get_active_order_by_key,
    should_create_position,
    transition_order,
)
from Backend.application.paper_trade_store import create_paper_trade
from Backend.application.position_store import create_open_position
from Backend.application.risk_gate import evaluate_risk_gate, validate_order_risk
from Backend.application.signal_quality import decide_signal
from Backend.application.signal_validation import diagnose_signal_run, validate_signals
from Backend.application.subscriptions import SubscriptionAccess, subscription_access
from Backend.application.trade_qualification_engine import (
    TradeQualification,
    TradeQualificationEngine,
)
from Backend.application.trading_engine_upgrade import (
    scale_position,
    submit_paper_basket,
    trading_engine_dashboard,
)
from Backend.application.trading_service import TradingService
from Backend.config import Provider
from Backend.core.config import get_settings
from Backend.core.database import get_db
from Backend.domain.engine.order_factory import ExecutionEngine
from Backend.domain.execution_constraints import (
    apply_order_constraints,
    requested_quantity,
    validate_execution_constraints,
)
from Backend.domain.models.signal import StrategySignal
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User
from Backend.infrastructure.broker.broker_client import BrokerClient, broker_client_for_mode
from Backend.infrastructure.broker.dhan_status import check_dhan_profile
from Backend.presentation.api.market_api import get_price
from Backend.presentation.api.roles import current_user, require_trade_execute

router = APIRouter()
market_service = MarketDataService()

AUTO_SCAN_STRATEGIES = [
    "amd",
    "breakout",
    "btst",
    "cbt",
    "crt_tbs",
    "mean_reversion",
    "mtf",
    "mtfa",
    "supply_demand",
]
MAX_ENTRY_PRICE_DEVIATION: Final[float] = 0.02


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AutoPaperExecutionRequest(BaseModel):
    symbol: str = Field(default="NIFTY", min_length=1, max_length=30)
    interval: Literal["1m", "3m", "5m", "10m", "15m", "30m", "1h", "1d"] = "1m"
    period: Literal["1d", "5d", "1mo", "3mo", "6mo", "1y"] = "1d"
    capital: float = Field(default=100_000.0, gt=0, le=100_000_000)
    risk_pct: float = Field(default=2.0, gt=0, le=10)
    rr_ratio: float = Field(default=2.0, gt=0, le=10)
    strategies: list[str] = Field(default_factory=list)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("Symbol cannot be empty.")
        return value

    @field_validator("strategies")
    @classmethod
    def normalize_strategies(cls, values: list[str]) -> list[str]:
        return [value.strip().lower() for value in values if value.strip()]


class TradingEngineBasketLeg(BaseModel):
    strategy: str = Field(default="manual_basket", min_length=1, max_length=100)
    symbol: str = Field(default="NIFTY", min_length=1, max_length=30)
    side: Literal["BUY", "SELL"] = "BUY"
    quantity: int = Field(default=1, gt=0, le=100_000)
    entry: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    target: float = Field(gt=0)
    trailing_stop_loss: float | None = Field(default=None, gt=0)
    trailing_stop_pct: float | None = Field(default=None, gt=0, le=100)
    score: float = Field(default=0.0, ge=0, le=100)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("Symbol cannot be empty.")
        return value

    @field_validator("strategy")
    @classmethod
    def normalize_strategy(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_price_shape(self) -> "TradingEngineBasketLeg":
        valid = (
            self.stop_loss < self.entry < self.target
            if self.side == "BUY"
            else self.target < self.entry < self.stop_loss
        )
        if not valid:
            expected = "stop_loss < entry < target" if self.side == "BUY" else "target < entry < stop_loss"
            raise ValueError(f"{self.side} order requires {expected}.")
        return self


class TradingEngineBasketRequest(BaseModel):
    execution_mode: Literal["paper", "live"] = "paper"
    reason: str | None = Field(default=None, max_length=500)
    legs: list[TradingEngineBasketLeg] = Field(min_length=1, max_length=50)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class TradingEngineScaleRequest(BaseModel):
    execution_mode: Literal["paper", "live"] = "paper"
    action: Literal["scale_in", "scale_out", "increase", "decrease"]
    quantity: int = Field(gt=0, le=100_000)
    price: float | None = Field(default=None, gt=0)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def get_engine() -> ExecutionEngine:
    return ExecutionEngine()


def _execution_mode(
    value: str = Header(default="paper", alias="X-QuantGrid-Mode"),
) -> str:
    mode = value.strip().lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(status_code=400, detail="Invalid execution mode.")
    return mode


def _require_engine_role(actor: User) -> None:
    if actor.role not in {"admin", "developer", "trader"}:
        raise HTTPException(status_code=403, detail="This role cannot perform this action.")


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


def _is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto.split(",", 1)[0].strip().lower() == "https"


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _model_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def _strategy_candles(response: dict[str, Any]) -> list[dict[str, Any]]:
    candles = list(response.get("candles") or [])
    if response.get("volume_status") == "not_reported_for_index":
        for candle in candles:
            candle["volume"] = None
    return candles


def _load_candles(symbol: str, interval: str, limit: int = 100) -> list[dict[str, Any]]:
    candles = latest_candles(symbol, interval, limit)
    if candles:
        return candles
    try:
        return _strategy_candles(
            market_service.get_candles(symbol, interval=interval, period="1d", limit=limit)
        )
    except Exception:
        return []


def _response(
    status_value: str,
    signal: StrategySignal | None,
    reason: str,
    execution_mode: str,
    *,
    symbol: str | None = None,
    strategy: str | None = None,
    diagnostics: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status_value,
        "symbol": (symbol or (signal.symbol if signal else "")).upper(),
        "strategy": strategy if strategy is not None else (signal.strategy_name if signal else None),
        "signal": signal.side if signal else None,
        "entry": _safe_float(signal.entry_price) if signal else None,
        "stop": _safe_float(signal.stop_loss) if signal else None,
        "target": _safe_float(signal.target_price) if signal else None,
        "trailing_stop_loss": _safe_float(signal.trailing_stop_loss) if signal else None,
        "trailing_stop_pct": _safe_float(signal.trailing_stop_pct) if signal else None,
        "reason": reason,
        "execution_mode": execution_mode,
        "strategy_diagnostics": diagnostics or {},
    }
    result.update(extra)
    if signal:
        qualification = (getattr(signal, "metadata", {}) or {}).get("trade_qualification")
        if qualification is not None:
            result.setdefault("trade_qualification", qualification)
    return result


def _risk_fields(decision: Any) -> dict[str, Any]:
    payload = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision or {})
    return {
        "allowed": bool(payload.get("allowed")),
        "risk_reason": str(payload.get("reason") or "UNKNOWN"),
        "risk_amount": _safe_float(payload.get("risk_amount")) or 0.0,
        "max_allowed_risk": _safe_float(payload.get("max_allowed_risk")) or 0.0,
        "risk_decision": payload,
    }


def _tqe_fields(qualification: TradeQualification) -> dict[str, Any]:
    return {
        "trade_qualification": qualification.to_dict(),
        "tqe_score": qualification.score,
        "quality_grade": qualification.quality_grade,
        "market_context": qualification.market_context,
        "volume_status": qualification.volume_status,
        "volatility_status": qualification.volatility_status,
        "position_size": (
            qualification.position_sizing.position_size
            if qualification.position_sizing
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Validation and guardrails
# ---------------------------------------------------------------------------

def _signal_shape_error(signal: StrategySignal) -> str | None:
    try:
        entry = float(signal.entry_price)
        stop = float(signal.stop_loss)
        target = float(signal.target_price)
        trailing_stop = _safe_float(signal.trailing_stop_loss)
        trailing_pct = _safe_float(signal.trailing_stop_pct)
    except (TypeError, ValueError):
        return "Entry, stop, target, and trailing values must be numeric."

    side = str(signal.side or "").upper()
    if side not in {"BUY", "SELL"}:
        return "Signal side must be BUY or SELL."
    if min(entry, stop, target) <= 0:
        return "Entry, stop, and target must be positive."
    if side == "BUY" and not stop < entry < target:
        return "BUY signal requires stop < entry < target."
    if side == "SELL" and not target < entry < stop:
        return "SELL signal requires target < entry < stop."
    if trailing_pct is not None and trailing_pct <= 0:
        return "Trailing stop percent must be greater than 0."
    if trailing_stop is not None:
        if trailing_stop <= 0:
            return "Trailing stop price must be positive."
        if side == "BUY" and trailing_stop >= entry:
            return "BUY signal requires trailing stop below entry."
        if side == "SELL" and trailing_stop <= entry:
            return "SELL signal requires trailing stop above entry."
    return None


def _market_aligned(signal: StrategySignal) -> bool:
    try:
        quote = get_price(signal.symbol)
        if str(quote.get("source", "")).lower() in {"sample-fallback", "stored-live-cache"}:
            return False
        market_price = float(quote["price"])
        entry_price = float(signal.entry_price)
        return market_price > 0 and abs(entry_price - market_price) / market_price <= MAX_ENTRY_PRICE_DEVIATION
    except (KeyError, TypeError, ValueError, Exception):
        return False


def _qualify(
    signal: StrategySignal,
    candles_1m: list[dict[str, Any]],
    candles_15m: list[dict[str, Any]],
    execution_mode: str,
) -> TradeQualification | None:
    if len(candles_1m) < 20:
        return None
    qualification = TradeQualificationEngine().qualify(
        signal=signal,
        candles=candles_1m,
        capital=100_000,
        risk_pct=2,
        m15_candles=candles_15m,
        enforce_execution_checks=True,
        execution_mode=execution_mode,
    )
    signal.metadata.update(_tqe_fields(qualification))
    return qualification


def _broker_session_valid(settings: Any) -> bool:
    provider = str(getattr(settings, "broker_provider", "")).strip().lower()
    if not provider:
        return False
    if provider in {"dhan", str(Provider.DHAN).lower()}:
        try:
            return bool(check_dhan_profile(timeout=3.0).get("connected"))
        except Exception:
            return False
    return bool(getattr(settings, "broker_configured", False))


def _live_guardrail_error(
    request: Request,
    actor: User,
    signal: StrategySignal,
    settings: Any,
    candles_1m: list[dict[str, Any]],
    risk_decision: Any,
) -> str | None:
    if not _is_https(request) and not _env_true("LIVE_ALLOW_INSECURE"):
        return "Live trading requires HTTPS."
    if not settings.broker_live_enabled:
        return "Live trading requires BROKER_LIVE_ENABLED=true."
    if not settings.risk_engine_enabled:
        return "Live trading requires risk engine enabled."
    if getattr(settings, "market_data_provider", None) == "yahoo" and not getattr(settings, "allow_yahoo_for_live", False):
        return "Live trading requires trading-grade market data; Yahoo is paper/demo only."

    halt = kill_switch_status()
    if halt.get("active"):
        return f"Trading halted: {halt.get('reason') or 'Kill switch active'}"
    circuit = broker_circuit_status()
    if circuit.get("active"):
        return f"Broker circuit breaker active: {circuit.get('reason') or 'Broker unavailable'}"

    validation = validate_live_candle(candles_1m, interval="1m", mode="live")
    if not validation.valid_for_execution or str(validation.market_status).upper() != "LIVE MARKET":
        return f"Live trading requires fresh market data. Current status: {validation.market_status}"
    if actor.role not in {"admin", "trader"}:
        return "Live trading requires Trader or Admin role."
    if not settings.broker_configured:
        return "Live trading requires broker credentials."
    if not _broker_session_valid(settings):
        return "Live trading requires a valid broker session."
    if not risk_decision.allowed:
        return f"Risk engine rejected trade: {risk_decision.reason}"

    details = getattr(risk_decision, "details", {}) or {}
    daily_loss = max(0.0, -float(details.get("daily_pnl") or 0.0))
    max_daily_loss = float(details.get("max_daily_loss") or 0.0)
    if max_daily_loss > 0 and daily_loss >= max_daily_loss:
        return "Live trading blocked: maximum daily loss reached."
    if not settings.audit_logging_enabled:
        return "Live trading requires audit logging enabled."

    if _safe_float(signal.stop_loss) is None or float(signal.stop_loss) <= 0:
        return "Live trading requires a valid stop-loss."
    if _safe_float(signal.target_price) is None or float(signal.target_price) <= 0:
        return "Live trading requires a valid target."
    if not _env_true("QUANTGRID_ALLOW_APP_MANAGED_STOPS"):
        return "Live trading requires broker-native stop protection."

    try:
        monitor_interval = float(os.getenv("QUANTGRID_EXIT_MONITOR_INTERVAL_SECONDS", "0"))
    except ValueError:
        monitor_interval = 0.0
    monitor_ready = (
        _env_true("QUANTGRID_EXIT_MONITOR_ENABLED")
        and os.getenv("QUANTGRID_EXIT_MONITOR_MODE", "").strip().lower() == "live"
        and 1 <= monitor_interval <= 10
    )
    if not monitor_ready:
        return "App-managed stops require a live Exit Monitor with a 1-10 second interval."
    return None


# ---------------------------------------------------------------------------
# Audit and lifecycle helpers
# ---------------------------------------------------------------------------

def _audit_result(db: Session, request: Request, actor: User, result: dict[str, Any]) -> None:
    submitted = result.get("status") in {"paper_order_submitted", "live_order_submitted"}
    action = result["status"] if submitted else "execution_blocked"
    metadata = {
        key: result.get(key)
        for key in (
            "strategy", "signal", "reason", "execution_mode", "risk_decision",
            "trade_qualification", "quality_grade", "tqe_score", "local_order_id",
            "broker_order_id", "broker_status", "broker_order", "raw_safe_broker_response",
        )
        if result.get(key) is not None
    }
    metadata["status"] = "submitted" if submitted else "rejected"
    write_audit_log(db, action=action, actor=actor, target_type="symbol", target_id=result.get("symbol"), request=request, metadata=metadata)


def _audit_risk(db: Session, request: Request, actor: User, signal: StrategySignal, decision: Any) -> None:
    payload = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision or {})
    allowed = bool(payload.get("allowed"))
    write_audit_log(
        db,
        action="risk_decision",
        actor=actor,
        target_type="symbol",
        target_id=signal.symbol,
        request=request,
        metadata={"strategy": signal.strategy_name, "side": signal.side, "status": "allowed" if allowed else "rejected", "risk_decision": payload},
    )
    if not allowed and str(payload.get("reason", "")).upper() == "MAX_DAILY_LOSS_EXCEEDED":
        write_audit_log(db, action="kill_switch_activated", actor=actor, target_type="symbol", target_id=signal.symbol, request=request, metadata={"reason": payload.get("reason"), "risk_decision": payload})


def _transition(
    local_order: dict[str, Any] | None,
    new_status: str,
    *,
    db: Session | None,
    request: Request | None,
    actor: User | None,
    reason: str,
    broker: Any = None,
) -> dict[str, Any] | None:
    if local_order is None:
        return None
    updated, old_status = transition_order(
        local_order_id=local_order["local_order_id"],
        status=new_status,
        status_reason=reason,
        broker_order_id=getattr(broker, "broker_order_id", None),
        broker_status=getattr(broker, "status", None),
        entry_price=getattr(broker, "price", None),
    )
    if db is not None and request is not None and actor is not None:
        write_audit_log(
            db,
            action="order_status_transition",
            actor=actor,
            target_type="order",
            target_id=updated["local_order_id"],
            request=request,
            metadata={"from_status": old_status, "to_status": updated.get("status"), "status_reason": reason, "broker_response": broker.to_dict() if broker else None},
        )
    return updated


def _create_lifecycle(
    order: Any,
    signal: StrategySignal,
    execution_mode: str,
    db: Session | None,
    request: Request | None,
    actor: User | None,
) -> dict[str, Any]:
    key = f"{signal.symbol.upper()}:{signal.side.upper()}:{signal.strategy_name.upper()}"
    duplicate = get_active_order_by_key(key)
    if duplicate:
        raise ValueError(f"DUPLICATE_ACTIVE_ORDER: {duplicate['local_order_id']}")
    local = create_order({
        "order_key": key,
        "strategy": signal.strategy_name,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "entry_price": order.price,
        "stop_loss": order.stop_loss,
        "target": order.target_price,
        "trailing_stop_loss": order.trailing_stop_loss,
        "trailing_stop_pct": order.trailing_stop_pct,
        "execution_mode": execution_mode,
        "status": "requested",
        "status_reason": "Order accepted for risk review.",
    })
    if db is not None and request is not None and actor is not None:
        write_audit_log(
            db,
            action="order_status_transition",
            actor=actor,
            target_type="order",
            target_id=local["local_order_id"],
            request=request,
            metadata={"from_status": "new", "to_status": "requested"},
        )
    return local


def _persist_trade_and_position(
    signal: StrategySignal,
    broker_status: Any,
    order_status: str,
    result_status: str,
    score: float = 0.0,
) -> None:
    create_paper_trade({
        "strategy": signal.strategy_name,
        "symbol": signal.symbol,
        "side": signal.side,
        "entry": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "target": signal.target_price,
        "trailing_stop_loss": signal.trailing_stop_loss,
        "trailing_stop_pct": signal.trailing_stop_pct,
        "status": result_status,
        "pnl": 0.0,
        "reason": "OK",
        "broker_order_id": broker_status.broker_order_id,
        "broker_status": broker_status.status,
        "raw_safe_broker_response": broker_status.metadata.get("raw_safe"),
        "score": score,
        "signal_time": signal.signal_time.isoformat(),
    })
    if should_create_position(order_status):
        create_open_position({
            "broker_order_id": broker_status.broker_order_id,
            "symbol": signal.symbol,
            "side": signal.side,
            "quantity": requested_quantity(signal),
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "target": signal.target_price,
            "trailing_stop_loss": signal.trailing_stop_loss,
            "trailing_stop_pct": signal.trailing_stop_pct,
            "current_price": broker_status.price or signal.entry_price,
            "opened_at": signal.signal_time.isoformat(),
        })


# ---------------------------------------------------------------------------
# Shared execution pipeline
# ---------------------------------------------------------------------------

async def _execute_signal(
    signal: StrategySignal,
    execution_mode: str,
    engine: ExecutionEngine,
    candles_1m: list[dict[str, Any]],
    candles_15m: list[dict[str, Any]],
    *,
    db: Session,
    request: Request,
    actor: User,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def reject(reason: str, **extra: Any) -> dict[str, Any]:
        observe_rejected_order(reason, execution_mode)
        return _response("rejected", signal, reason, execution_mode, diagnostics=diagnostics, **extra)

    shape_error = _signal_shape_error(signal)
    if shape_error:
        return reject(shape_error, allowed=False)

    qualification = _qualify(signal, candles_1m, candles_15m, execution_mode)
    if qualification and not qualification.allowed:
        return reject(f"TQE_REJECTED: {qualification.reason}", allowed=False, **_tqe_fields(qualification))

    risk = validate_order_risk(signal, execution_mode=execution_mode, candles_1m=candles_1m)
    _audit_risk(db, request, actor, signal, risk)
    if not risk.allowed:
        return reject(risk.reason, **_risk_fields(risk))

    if execution_mode == "live":
        settings = get_settings()
        guardrail_error = _live_guardrail_error(request, actor, signal, settings, candles_1m, risk)
        if guardrail_error:
            return reject(guardrail_error, live_guardrail="failed", **_risk_fields(risk))
    else:
        validation = validate_live_candle(candles_1m, interval="1m", mode="paper")
        market_status = str(validation.market_status)
        if not validation.valid_for_execution or market_status.upper() != "LIVE MARKET":
            return reject(f"MARKET_NOT_LIVE_FOR_EXECUTION: {market_status}", allowed=False, validation=validation.model_dump())

        decision = decide_signal(signal, candles_1m=candles_1m, candles_15m=candles_15m)
        gate = evaluate_risk_gate(decision)
        if not gate.allowed:
            return reject(gate.reason, allowed=False, decision=decision.to_dict(), **_risk_fields(risk))
        if not _market_aligned(signal):
            return reject("Signal entry price is not aligned with market price.", allowed=False, decision=decision.to_dict(), **_risk_fields(risk))

    constraints = validate_execution_constraints(signal)
    if not constraints.accepted:
        return reject(
            constraints.reason,
            allowed=False,
            lot_size=constraints.lot_size,
            rounded_quantity=constraints.quantity,
            required_margin=constraints.required_margin,
            **_risk_fields(risk),
        )

    order = apply_order_constraints(engine.order_from_signal(signal), constraints, requested_quantity(signal))
    try:
        local = _create_lifecycle(order, signal, execution_mode, db, request, actor)
    except ValueError as exc:
        if str(exc).startswith("DUPLICATE_ACTIVE_ORDER"):
            return reject(str(exc), broker_confirmed=False, **_risk_fields(risk))
        raise

    local = _transition(local, "risk_approved", db=db, request=request, actor=actor, reason="Risk checks approved order.")
    broker = broker_client_for_mode(execution_mode)

    try:
        local = _transition(local, "broker_submitted", db=db, request=request, actor=actor, reason="Submitted to broker adapter.")
        if execution_mode == "paper":
            oms = await OrderManagementService(broker).submit_order(
                order,
                signal,
                {
                    "local_order_id": local["local_order_id"] if local else None,
                    "prevalidated_risk": {
                        "allowed": risk.allowed,
                        "reasons": [risk.reason],
                        "risk_score": risk.details.get("risk_engine", {}).get("risk_score", 100),
                        "blocked_by": risk.details.get("risk_engine", {}).get("blocked_by", []),
                        "warnings": risk.details.get("risk_engine", {}).get("warnings", []),
                    },
                },
            )
            if not oms.accepted:
                _transition(local, "rejected", db=db, request=request, actor=actor, reason=f"OMS_{oms.status.upper()}: {'; '.join(oms.reasons)}", broker=oms)
                return reject(f"OMS_{oms.status.upper()}: {'; '.join(oms.reasons)}", oms=oms.to_dict(), broker_confirmed=False, **_risk_fields(risk))
            broker_order_id = str(oms.broker_order_id)
        else:
            placed = await broker.place_order(order)
            broker_order_id = str(placed.broker_order_id)
            local = _transition(local, "broker_submitted", db=db, request=request, actor=actor, reason="Broker accepted submission.", broker=placed)

        broker_status = await broker.get_order_status(broker_order_id)
    except Exception as exc:
        if execution_mode == "live":
            record_broker_failure(reason=str(exc), db=db, actor=actor, request=request, metadata={"symbol": signal.symbol, "side": signal.side, "phase": "broker_submit"})
        _transition(local, "failed", db=db, request=request, actor=actor, reason=f"BROKER_FAILURE: {exc}")
        return reject(f"BROKER_FAILURE: {exc}", broker_confirmed=False, **_risk_fields(risk))

    if not broker_status.confirmed or broker_status.status in {"rejected", "failed", "not_found"}:
        mapped = broker_status_to_order_status(broker_status.status, confirmed=broker_status.confirmed)
        final_status = mapped if mapped in {"rejected", "failed", "cancelled"} else "rejected"
        _transition(local, final_status, db=db, request=request, actor=actor, reason=f"BROKER_NOT_CONFIRMED: {broker_status.status}", broker=broker_status)
        return reject(
            f"BROKER_NOT_CONFIRMED: {broker_status.status}",
            broker_order_id=broker_status.broker_order_id,
            broker_status=broker_status.status,
            broker_confirmed=False,
            broker_order=broker_status.to_dict(),
            raw_safe_broker_response=broker_status.metadata.get("raw_safe"),
            **_risk_fields(risk),
        )

    order_status = broker_status_to_order_status(broker_status.status, confirmed=True)
    local = _transition(local, order_status, db=db, request=request, actor=actor, reason=f"Broker status confirmed: {broker_status.status}", broker=broker_status)
    result_status = "live_order_submitted" if execution_mode == "live" else "paper_order_submitted"
    score = 0.0
    if execution_mode == "paper":
        score = decide_signal(signal, candles_1m=candles_1m, candles_15m=candles_15m).score
    _persist_trade_and_position(signal, broker_status, order_status, result_status, score)
    observe_paper_order(result_status, signal.strategy_name, signal.symbol)

    return _response(
        result_status,
        signal,
        "OK",
        execution_mode,
        diagnostics=diagnostics,
        **_risk_fields(risk),
        **(_tqe_fields(qualification) if qualification else {}),
        order=jsonable_encoder(order),
        broker_order_id=broker_status.broker_order_id,
        local_order_id=local.get("local_order_id") if local else None,
        broker_status=broker_status.status,
        broker_confirmed=True,
        broker_order=broker_status.to_dict(),
        raw_safe_broker_response=broker_status.metadata.get("raw_safe"),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/trading-engine/dashboard")
async def get_trading_engine_dashboard(actor: User = Depends(current_user)):
    _require_engine_role(actor)
    return trading_engine_dashboard()


@router.post("/trading-engine/basket")
async def submit_trading_engine_basket(
    payload: TradingEngineBasketRequest,
    request: Request,
    actor: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_engine_role(actor)
    try:
        result = submit_paper_basket(
            legs=[_model_dict(leg) for leg in payload.legs],
            execution_mode=payload.execution_mode,
            reason=payload.reason,
        )
    except ValueError as exc:
        write_audit_log(db, action="paper_basket_blocked", actor=actor, target_type="basket", target_id="paper", request=request, metadata={"reason": str(exc), "execution_mode": payload.execution_mode})
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    write_audit_log(db, action="paper_basket_submitted", actor=actor, target_type="basket", target_id=result["basket_id"], request=request, metadata={"status": result["status"], "created_count": result["created_count"], "error_count": result["error_count"], "execution_mode": result["execution_mode"]})
    return result


@router.post("/trading-engine/positions/{position_id}/scale")
async def submit_trading_engine_scale(
    position_id: int,
    payload: TradingEngineScaleRequest,
    request: Request,
    actor: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _require_engine_role(actor)
    try:
        result = scale_position(position_id, action=payload.action, quantity=payload.quantity, price=payload.price, reason=payload.reason, execution_mode=payload.execution_mode)
    except ValueError as exc:
        write_audit_log(db, action="position_scale_blocked", actor=actor, target_type="position", target_id=position_id, request=request, metadata={"reason": str(exc), "execution_mode": payload.execution_mode, "action": payload.action})
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    write_audit_log(db, action="position_scaled", actor=actor, target_type="position", target_id=position_id, request=request, metadata={"action": result["status"], "old_quantity": result["old_quantity"], "new_quantity": result["new_quantity"], "price": result["price"], "realized_pnl": result["realized_pnl"], "execution_mode": result["execution_mode"]})
    return result


@router.post("/auto-paper")
async def auto_paper_order(
    payload: AutoPaperExecutionRequest,
    request: Request,
    engine: ExecutionEngine = Depends(get_engine),
    actor: User = Depends(require_trade_execute),
    access: SubscriptionAccess = Depends(subscription_access),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    if not access.can("paper_trade.automated"):
        raise HTTPException(status_code=403, detail={"error": "subscription_required", "feature": "paper_trade.automated", "current_plan": access.snapshot["plan_code"].upper(), "message": "Automated paper trading requires a Pro or Premium plan."})
    if execution_mode != "paper":
        return _response("rejected", None, "Auto execution is paper-only.", execution_mode, symbol=payload.symbol, allowed=False)

    halt = kill_switch_status()
    if halt.get("active"):
        result = _response("rejected", None, f"KILL_SWITCH_ACTIVE: {halt.get('reason') or 'Trading halted'}", execution_mode, symbol=payload.symbol, allowed=False, kill_switch=halt)
        _audit_result(db, request, actor, result)
        alert_execution_event(result)
        return result

    base_response = market_service.get_candles(payload.symbol, interval=payload.interval, period=payload.period, limit=150)
    candles = _strategy_candles(base_response)
    candles_5m = _strategy_candles(market_service.get_candles(payload.symbol, interval="5m", period=payload.period, limit=150))
    candles_15m = _strategy_candles(market_service.get_candles(payload.symbol, interval="15m", period=payload.period, limit=150))
    validation = validate_live_candle(candles, interval=payload.interval, mode="paper", source=base_response.get("source"), provider_fetched_at=base_response.get("fetched_at"))

    service = TradingService()
    strategies = payload.strategies or AUTO_SCAN_STRATEGIES
    diagnostics: dict[str, Any] = {}

    for strategy in strategies:
        try:
            raw = service.run_strategy(
                strategy_name=strategy,
                data=candles,
                symbol=payload.symbol,
                capital=payload.capital,
                risk_pct=payload.risk_pct,
                rr_ratio=payload.rr_ratio,
                params={"mtf_candles": candles_5m, "htf_candles": candles_15m},
            )
            observe_signal_generation(strategy, "success")
            validated, source = validate_signals(raw, symbol=payload.symbol, candles=candles, candle_source=base_response.get("source"))
            diagnostics[strategy] = {
                "raw_signals": len(raw),
                "validated_signals": len(validated),
                "data_source": source,
                "market_status": validation.market_status,
                "validation": validation.model_dump(),
                "diagnostics": diagnose_signal_run(raw, symbol=payload.symbol, candles=candles, candle_source=base_response.get("source")),
            }
            if not validated:
                continue
            signal = validated[0]
            diagnostics[strategy]["selected_signal"] = serialize_signal(signal)
        except Exception as exc:
            observe_signal_generation(strategy, "error")
            diagnostics[strategy] = {"raw_signals": 0, "validated_signals": 0, "market_status": validation.market_status, "validation": validation.model_dump(), "diagnostics": [f"Strategy scan failed: {exc}"]}
            continue

        result = await _execute_signal(signal, execution_mode, engine, candles, candles_15m, db=db, request=request, actor=actor, diagnostics=diagnostics)
        _audit_result(db, request, actor, result)
        alert_execution_event(result)
        return result

    result = _response("no_trade", None, "No validated signal found across auto-scan strategies.", execution_mode, symbol=payload.symbol, diagnostics=diagnostics, candles_analyzed=len(candles), strategies_checked=strategies, validation=validation.model_dump())
    alert_execution_event(result)
    return result


@router.post("/auto-paper/jobs")
async def enqueue_auto_paper_order(
    payload: AutoPaperExecutionRequest,
    request: Request,
    actor: User = Depends(require_trade_execute),
    access: SubscriptionAccess = Depends(subscription_access),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    if not access.can("paper_trade.automated"):
        raise HTTPException(status_code=403, detail="Automated paper trading requires a Pro or Premium plan.")
    if execution_mode != "paper":
        raise HTTPException(status_code=400, detail="Auto-paper jobs are paper-only.")

    job = enqueue_job("auto-paper", _model_dict(payload), metadata={"symbol": payload.symbol, "strategy": ",".join(payload.strategies or AUTO_SCAN_STRATEGIES), "interval": payload.interval, "period": payload.period})
    write_audit_log(db, action="trading_job_created", actor=actor, target_type="job", target_id=job["job_id"], request=request, metadata={"job_type": "auto-paper", "symbol": payload.symbol, "status": "queued"})
    return job


@router.post("/order")
async def place_order(
    signal: StrategySignal,
    request: Request,
    engine: ExecutionEngine = Depends(get_engine),
    actor: User = Depends(require_trade_execute),
    access: SubscriptionAccess = Depends(subscription_access),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    feature = "live_trade.execute" if execution_mode == "live" else "paper_trade.manual"
    if not access.can(feature):
        raise HTTPException(status_code=403, detail={"error": "subscription_required", "feature": feature, "current_plan": access.snapshot["plan_code"].upper(), "message": "Your active subscription does not include this execution mode."})

    write_audit_log(db, action="execution_triggered", actor=actor, target_type="symbol", target_id=signal.symbol, request=request, metadata={"mode": execution_mode, "strategy": signal.strategy_name})

    if execution_mode == "live" and not getattr(get_settings(), "live_trading_enabled", False):
        raise HTTPException(status_code=403, detail="Live trading is disabled. Paper trading only.")

    candles_1m = _load_candles(signal.symbol, "1m")
    candles_15m = _load_candles(signal.symbol, "15m")
    result = await _execute_signal(signal, execution_mode, engine, candles_1m, candles_15m, db=db, request=request, actor=actor)
    _audit_result(db, request, actor, result)
    alert_execution_event(result)
    return result