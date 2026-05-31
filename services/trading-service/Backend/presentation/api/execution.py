from typing import Any
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from Backend.application.candle_validation import validate_live_candle
from Backend.application.dto import serialize_signal
from Backend.application.job_queue import enqueue_job
from Backend.core.config import get_settings
from Backend.core.database import get_db
from Backend.application.notifications import alert_execution_event
from Backend.application.order_store import (
    broker_status_to_order_status,
    create_order,
    should_create_position,
    transition_order,
)
from Backend.application.paper_trade_store import create_paper_trade
from Backend.application.position_store import create_open_position
from Backend.application.risk_gate import evaluate_risk_gate, validate_order_risk
from Backend.application.signal_quality import decide_signal
from Backend.application.signal_validation import diagnose_signal_run, validate_signals
from Backend.application.trade_qualification_engine import TradeQualificationEngine, TradeQualification
from Backend.application.trading_service import TradingService
from Backend.domain.engine.execution_engine import ExecutionEngine
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
from Backend.presentation.api.market_api import get_candles, get_price
from Backend.application.market_data_store import latest_candles
from Backend.application.kill_switch import kill_switch_status
from Backend.application.monitoring import observe_paper_order, observe_rejected_order, observe_signal_generation
from Backend.presentation.api.roles import require_roles, require_trade_execute

router = APIRouter()
AUTO_SCAN_STRATEGIES = ["amd", "breakout", "btst", "crt_tbs", "mean_reversion", "mtf", "mtfa", "supply_demand"]


# dependency injection (cleaner + testable)
def get_engine():
    return ExecutionEngine()


def get_broker_client(execution_mode: str) -> BrokerClient:
    return broker_client_for_mode(execution_mode)


def _execution_mode(x_quantgrid_mode: str = Header(default="paper", alias="X-QuantGrid-Mode")) -> str:
    mode = x_quantgrid_mode.strip().lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid execution mode.")
    return mode


def _request_is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto.split(",", 1)[0].strip().lower() == "https"


def _allow_insecure_live() -> bool:
    return str(os.getenv("LIVE_ALLOW_INSECURE", "")).strip().lower() in {"1", "true", "yes"}


def _live_guardrail_failure(
    *,
    request: Request,
    actor: User,
    settings: Any,
    candles_1m: list[dict[str, Any]],
    risk_decision: Any,
) -> str | None:
    if not _request_is_https(request) and not _allow_insecure_live():
        return "Live trading requires HTTPS."
    if not settings.broker_live_enabled:
        return "Live trading requires BROKER_LIVE_ENABLED=true."
    if not settings.risk_engine_enabled:
        return "Live trading requires risk engine enabled."
    if getattr(settings, "market_data_provider", None) == "yahoo" and not getattr(settings, "allow_yahoo_for_live", False):
        return "Live trading requires trading-grade market data; Yahoo is paper/demo only."
    if kill_switch_status()["active"]:
        return "Trading halted by kill switch."
    market_validation = validate_live_candle(candles_1m, interval="1m", mode="live")
    if not market_validation.valid_for_execution:
        return f"Live trading requires fresh market data: {market_validation.market_status}."
    if actor.role not in {"admin", "trader"}:
        return "Live trading requires trader or admin role."
    if not settings.broker_configured:
        return "Live trading requires broker credentials."
    if not _broker_session_valid(settings):
        return "Live trading requires valid broker session."
    if not risk_decision.allowed:
        return f"Live trading rejected by risk engine: {risk_decision.reason}"
    details = risk_decision.details if hasattr(risk_decision, "details") else {}
    daily_pnl = float(details.get("daily_pnl") or 0.0)
    max_daily_loss = float(details.get("max_daily_loss") or 0.0)
    if abs(min(0.0, daily_pnl)) >= max_daily_loss:
        return "Live trading blocked: max daily loss breached."
    if not settings.audit_logging_enabled:
        return "Live trading requires audit logging enabled."
    return None


def _broker_session_valid(settings: Any) -> bool:
    provider = str(settings.broker_provider or "").lower()
    if provider == "dhan":
        return bool(check_dhan_profile(timeout=3.0).get("connected"))
    return bool(settings.broker_configured and provider)


def _market_aligned(signal: StrategySignal) -> bool:
    price_response = get_price(signal.symbol)
    if price_response.get("source") != "yahoo-finance":
        return False
    market_price = price_response.get("price")
    if market_price is None or float(market_price) <= 0:
        return False
    return abs(float(signal.entry_price) - float(market_price)) / float(market_price) <= 0.02


class AutoPaperExecutionRequest(BaseModel):
    symbol: str = "NIFTY"
    interval: str = "1m"
    period: str = "1d"
    capital: float = Field(default=100000, gt=0)
    risk_pct: float = Field(default=1, gt=0)
    rr_ratio: float = Field(default=2, gt=0)
    strategies: list[str] | None = None


def _paper_response(
    *,
    status_value: str,
    symbol: str,
    strategy: str | None,
    signal: StrategySignal | None,
    reason: str,
    execution_mode: str,
    strategy_diagnostics: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "status": status_value,
        "symbol": symbol.upper(),
        "strategy": strategy,
        "signal": signal.side if signal else None,
        "entry": float(signal.entry_price) if signal else None,
        "stop": float(signal.stop_loss) if signal else None,
        "target": float(signal.target_price) if signal else None,
        "reason": reason,
        "execution_mode": execution_mode,
        "strategy_diagnostics": strategy_diagnostics or {},
    }
    if extra:
        response.update(extra)
    if signal and "trade_qualification" in signal.metadata:
        response.setdefault("trade_qualification", signal.metadata["trade_qualification"])
    return response


def _audit_execution_result(
    db: Session,
    request: Request,
    actor: User,
    result: dict[str, Any],
) -> None:
    submitted = result.get("status") in {"paper_order_submitted", "live_order_submitted"}
    action = "live_order_submitted" if result.get("status") == "live_order_submitted" else "paper_order_submitted"
    write_audit_log(
        db,
        action=action if submitted else "execution_blocked",
        actor=actor,
        target_type="symbol",
        target_id=result.get("symbol"),
        request=request,
        metadata={
            "strategy": result.get("strategy"),
            "side": result.get("signal"),
            "reason": result.get("reason"),
            "status": "submitted" if submitted else "rejected",
            "risk_decision": result.get("risk_decision"),
            "trade_qualification": result.get("trade_qualification"),
            "quality_grade": result.get("quality_grade"),
            "tqe_score": result.get("tqe_score"),
            "local_order_id": result.get("local_order_id"),
            "broker_order_id": result.get("broker_order_id"),
            "broker_status": result.get("broker_status"),
            "broker_order": result.get("broker_order"),
            "raw_safe_broker_response": result.get("raw_safe_broker_response"),
        },
    )


def _audit_order_transition(
    db: Session | None,
    request: Request | None,
    actor: User | None,
    order: dict[str, Any],
    previous_status: str,
    broker_response: dict[str, Any] | None = None,
) -> None:
    if db is None or request is None or actor is None:
        return
    write_audit_log(
        db,
        action="order_status_transition",
        actor=actor,
        target_type="order",
        target_id=order["local_order_id"],
        request=request,
        metadata={
            "status": order["status"],
            "from_status": previous_status,
            "to_status": order["status"],
            "status_reason": order.get("status_reason"),
            "broker_order_id": order.get("broker_order_id"),
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "quantity": order.get("quantity"),
            "broker_response": broker_response,
        },
    )


def _create_lifecycle_order(
    order: Any,
    *,
    db: Session | None,
    request: Request | None,
    actor: User | None,
) -> dict[str, Any]:
    local_order = create_order(
        {
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "entry_price": order.price,
            "status": "requested",
            "status_reason": "Order request accepted for risk review.",
        }
    )
    _audit_order_transition(db, request, actor, local_order, "new")
    return local_order


def _transition_lifecycle_order(
    local_order: dict[str, Any] | None,
    status_value: str,
    *,
    db: Session | None,
    request: Request | None,
    actor: User | None,
    reason: str | None = None,
    broker_order_id: str | None = None,
    entry_price: float | None = None,
    broker_response: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if local_order is None:
        return None
    updated, previous = transition_order(
        local_order["local_order_id"],
        status_value,
        status_reason=reason,
        broker_order_id=broker_order_id,
        entry_price=entry_price,
    )
    _audit_order_transition(db, request, actor, updated, previous, broker_response)
    return updated


def _reject_live_guardrail(
    *,
    db: Session,
    request: Request,
    actor: User,
    signal: StrategySignal,
    reason: str,
    execution_mode: str,
    risk_decision: Any,
) -> dict[str, Any]:
    result = _paper_response(
        status_value="rejected",
        symbol=signal.symbol,
        strategy=signal.strategy_name,
        signal=signal,
        reason=reason,
        execution_mode=execution_mode,
        extra={**_risk_response_fields(risk_decision), "live_guardrail": "failed"},
    )
    write_audit_log(
        db,
        action="execution_blocked",
        actor=actor,
        target_type="symbol",
        target_id=signal.symbol,
        request=request,
        metadata={
            "reason": reason,
            "status": "rejected",
            "strategy": signal.strategy_name,
            "side": signal.side,
            "risk_decision": result.get("risk_decision"),
            "live_guardrail": "failed",
        },
    )
    return result


def _audit_risk_decision(
    db: Session,
    request: Request,
    actor: User,
    *,
    symbol: str,
    strategy: str | None,
    side: str | None,
    risk_decision: Any,
) -> None:
    payload = risk_decision.to_dict() if hasattr(risk_decision, "to_dict") else dict(risk_decision or {})
    write_audit_log(
        db,
        action="risk_decision",
        actor=actor,
        target_type="symbol",
        target_id=symbol,
        request=request,
        metadata={
            "strategy": strategy,
            "side": side,
            "status": "allowed" if payload.get("allowed") else "rejected",
            "risk_decision": payload,
        },
    )
    if not payload.get("allowed") and str(payload.get("reason") or "").upper() == "MAX_DAILY_LOSS_EXCEEDED":
        write_audit_log(
            db,
            action="kill_switch_activated",
            actor=actor,
            target_type="symbol",
            target_id=symbol,
            request=request,
            metadata={
                "strategy": strategy,
                "side": side,
                "status": "activated",
                "reason": "MAX_DAILY_LOSS_EXCEEDED",
                "risk_decision": payload,
            },
        )


def _risk_response_fields(risk_decision: Any) -> dict[str, Any]:
    payload = risk_decision.to_dict() if hasattr(risk_decision, "to_dict") else dict(risk_decision or {})
    return {
        "allowed": bool(payload.get("allowed")),
        "reason": str(payload.get("reason") or "UNKNOWN"),
        "risk_amount": float(payload.get("risk_amount") or 0.0),
        "max_allowed_risk": float(payload.get("max_allowed_risk") or 0.0),
        "risk_decision": payload,
    }


def _tqe_response_fields(qualification: TradeQualification) -> dict[str, Any]:
    payload = qualification.to_dict()
    return {
        "trade_qualification": payload,
        "tqe_score": qualification.score,
        "quality_grade": qualification.quality_grade,
        "market_context": qualification.market_context,
        "volume_status": qualification.volume_status,
        "volatility_status": qualification.volatility_status,
        "position_size": qualification.position_sizing.position_size,
    }


def _execution_qualification(
    signal: StrategySignal,
    *,
    candles_1m: list[dict[str, Any]],
    candles_15m: list[dict[str, Any]] | None,
    execution_mode: str,
) -> TradeQualification | None:
    if len(candles_1m) < 20:
        return None
    qualification = TradeQualificationEngine().qualify(
        signal,
        candles=candles_1m,
        capital=100_000,
        risk_pct=1,
        m15_candles=candles_15m,
        enforce_execution_checks=True,
        execution_mode=execution_mode,
    )
    signal.metadata["trade_qualification"] = qualification.to_dict()
    signal.metadata["tqe_score"] = qualification.score
    signal.metadata["quality_grade"] = qualification.quality_grade
    signal.metadata["market_context"] = qualification.market_context
    signal.metadata["volume_status"] = qualification.volume_status
    signal.metadata["volatility_status"] = qualification.volatility_status
    return qualification


def _trade_shape_reason(signal: StrategySignal) -> str | None:
    try:
        entry = float(signal.entry_price)
        stop = float(signal.stop_loss)
        target = float(signal.target_price)
    except (TypeError, ValueError):
        return "Entry, stop, and target must be numeric."
    side = str(signal.side or "").upper()
    if side not in {"BUY", "SELL"}:
        return "Signal side must be BUY or SELL."
    if entry <= 0 or stop <= 0 or target <= 0:
        return "Entry, stop, and target must be positive."
    if side == "BUY" and not stop < entry < target:
        return "BUY signal requires stop < entry < target."
    if side == "SELL" and not target < entry < stop:
        return "SELL signal requires target < entry < stop."
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk <= 0 or reward <= 0:
        return "Risk/reward is invalid."
    return None


def _strategy_candles(candles_response: dict[str, Any]) -> list[dict[str, Any]]:
    candles = list(candles_response.get("candles", []))
    if candles_response.get("volume_status") == "not_reported_for_index":
        return [{**candle, "volume": None} for candle in candles]
    return candles


async def _submit_paper_signal(
    signal: StrategySignal,
    *,
    engine: ExecutionEngine,
    execution_mode: str,
    candles_1m: list[dict[str, Any]] | None = None,
    candles_15m: list[dict[str, Any]] | None = None,
    strategy_diagnostics: dict[str, Any] | None = None,
    broker_client: BrokerClient | None = None,
    db: Session | None = None,
    request: Request | None = None,
    actor: User | None = None,
) -> dict[str, Any]:
    if execution_mode != "paper":
        observe_rejected_order("paper_mode_required", execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason="Paper execution requires X-QuantGrid-Mode: paper.",
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
        )

    shape_reason = _trade_shape_reason(signal)
    if shape_reason:
        observe_rejected_order(shape_reason, execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=shape_reason,
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
        )

    candles_1m = candles_1m if candles_1m is not None else latest_candles(signal.symbol, "1m", 100)
    candles_15m = candles_15m if candles_15m is not None else latest_candles(signal.symbol, "15m", 100)
    if not candles_1m:
        try:
            candles_1m = _strategy_candles(get_candles(signal.symbol, interval="1m", period="1d", limit=100))
        except Exception:
            candles_1m = []
    candles_15m = latest_candles(signal.symbol, "15m", 100)
    if not candles_15m:
        try:
            candles_15m = _strategy_candles(get_candles(signal.symbol, interval="15m", period="1d", limit=100))
        except Exception:
            candles_15m = []
    if not candles_15m:
        try:
            candles_15m = _strategy_candles(get_candles(signal.symbol, interval="15m", period="1d", limit=100))
        except Exception:
            candles_15m = []
    qualification = _execution_qualification(
        signal,
        candles_1m=candles_1m,
        candles_15m=candles_15m,
        execution_mode=execution_mode,
    )
    if qualification is not None and not qualification.allowed:
        observe_rejected_order(qualification.reason, execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=f"TQE_REJECTED: {qualification.reason}",
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
            extra={"allowed": False, **_tqe_response_fields(qualification)},
        )
    risk_decision = validate_order_risk(signal, execution_mode=execution_mode, candles_1m=candles_1m)
    if not risk_decision.allowed:
        observe_rejected_order(risk_decision.reason, execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=risk_decision.reason,
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
            extra=_risk_response_fields(risk_decision),
        )
    candle_validation = validate_live_candle(candles_1m, interval="1m", mode="paper")
    decision = decide_signal(signal, candles_1m=candles_1m, candles_15m=candles_15m)
    gate = evaluate_risk_gate(decision)
    if not gate.allowed:
        observe_rejected_order(gate.reason, execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=gate.reason,
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
            extra={**_risk_response_fields(risk_decision), "allowed": False, "decision": decision.to_dict()},
        )

    if not _market_aligned(signal):
        observe_rejected_order("market_alignment_failed", execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason="Signal entry price is not aligned with market price.",
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
            extra={**_risk_response_fields(risk_decision), "allowed": False, "decision": decision.to_dict()},
        )

    constraints = validate_execution_constraints(signal)
    if not constraints.accepted:
        observe_rejected_order(constraints.reason, execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=constraints.reason,
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
            extra={
                "allowed": False,
                **_risk_response_fields(risk_decision),
                "decision": decision.to_dict(),
                "lot_size": constraints.lot_size,
                "rounded_quantity": constraints.quantity,
                "required_margin": constraints.required_margin,
            },
        )

    order = apply_order_constraints(
        engine.order_from_signal(signal),
        constraints,
        requested_quantity(signal),
    )
    lifecycle_order = _create_lifecycle_order(order, db=db, request=request, actor=actor)
    lifecycle_order = _transition_lifecycle_order(
        lifecycle_order,
        "risk_approved",
        db=db,
        request=request,
        actor=actor,
        reason="Risk engine approved order.",
    )
    broker_client = broker_client or broker_client_for_mode(execution_mode)
    try:
        lifecycle_order = _transition_lifecycle_order(
            lifecycle_order,
            "broker_submitted",
            db=db,
            request=request,
            actor=actor,
            reason="Submitted to broker adapter.",
        )
        broker_order = await broker_client.place_order(order)
        lifecycle_order = _transition_lifecycle_order(
            lifecycle_order,
            "broker_submitted",
            db=db,
            request=request,
            actor=actor,
            reason="Broker accepted submission.",
            broker_order_id=broker_order.broker_order_id,
            entry_price=broker_order.price,
            broker_response=broker_order.to_dict(),
        )
        broker_status = await broker_client.get_order_status(broker_order.broker_order_id)
    except Exception as exc:
        lifecycle_order = _transition_lifecycle_order(
            lifecycle_order,
            "failed",
            db=db,
            request=request,
            actor=actor,
            reason=f"BROKER_FAILURE: {exc}",
        )
        observe_rejected_order("broker_failure", execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=f"BROKER_FAILURE: {exc}",
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
            extra={**_risk_response_fields(risk_decision), "broker_confirmed": False},
        )

    if not broker_status.confirmed or broker_status.status in {"rejected", "failed", "not_found"}:
        mapped_status = broker_status_to_order_status(broker_status.status, confirmed=broker_status.confirmed)
        lifecycle_order = _transition_lifecycle_order(
            lifecycle_order,
            mapped_status if mapped_status in {"rejected", "failed", "cancelled"} else "rejected",
            db=db,
            request=request,
            actor=actor,
            reason=f"BROKER_NOT_CONFIRMED: {broker_status.status}",
            broker_order_id=broker_status.broker_order_id,
            entry_price=broker_status.price,
            broker_response=broker_status.to_dict(),
        )
        observe_rejected_order(f"broker_not_confirmed:{broker_status.status}", execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=f"BROKER_NOT_CONFIRMED: {broker_status.status}",
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
            extra={
                **_risk_response_fields(risk_decision),
                "broker_order_id": broker_status.broker_order_id,
                "broker_status": broker_status.status,
                "broker_confirmed": False,
                "broker_order": broker_status.to_dict(),
                "raw_safe_broker_response": broker_status.metadata.get("raw_safe"),
            },
        )

    order_status = broker_status_to_order_status(broker_status.status, confirmed=broker_status.confirmed)
    lifecycle_order = _transition_lifecycle_order(
        lifecycle_order,
        order_status,
        db=db,
        request=request,
        actor=actor,
        reason=f"Broker status confirmed: {broker_status.status}",
        broker_order_id=broker_status.broker_order_id,
        entry_price=broker_status.price or signal.entry_price,
        broker_response=broker_status.to_dict(),
    )
    result = _paper_response(
        status_value="paper_order_submitted",
        symbol=signal.symbol,
        strategy=signal.strategy_name,
        signal=signal,
        reason="OK",
        execution_mode=execution_mode,
        strategy_diagnostics=strategy_diagnostics,
        extra={
            **_risk_response_fields(risk_decision),
            **(_tqe_response_fields(qualification) if qualification is not None else {}),
            "source": "signal_based",
            "decision": decision.to_dict(),
            "order": jsonable_encoder(order),
            "broker_order_id": broker_status.broker_order_id,
            "local_order_id": lifecycle_order.get("local_order_id") if lifecycle_order else None,
            "broker_status": broker_status.status,
            "broker_confirmed": True,
            "broker_order": broker_status.to_dict(),
            "raw_safe_broker_response": broker_status.metadata.get("raw_safe"),
        },
    )
    create_paper_trade(
        {
            "strategy": signal.strategy_name,
            "symbol": signal.symbol,
            "side": signal.side,
            "entry": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "target": signal.target_price,
            "status": "paper_order_submitted",
            "pnl": 0.0,
            "reason": "OK",
            "broker_order_id": broker_status.broker_order_id,
            "score": decision.score,
            "tqe_score": qualification.score if qualification is not None else signal.metadata.get("tqe_score", 0),
            "quality_grade": qualification.quality_grade if qualification is not None else signal.metadata.get("quality_grade"),
            "regime": decision.regime,
            "signal_time": signal.signal_time.isoformat(),
            "broker_status": broker_status.status,
            "raw_safe_broker_response": broker_status.metadata.get("raw_safe"),
        }
    )
    if should_create_position(order_status):
        create_open_position(
            {
                "broker_order_id": broker_status.broker_order_id,
                "symbol": signal.symbol,
                "side": signal.side,
                "quantity": requested_quantity(signal),
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "target": signal.target_price,
                "current_price": broker_status.price or signal.entry_price,
                "opened_at": signal.signal_time.isoformat(),
            }
        )
    observe_paper_order("paper_order_submitted", signal.strategy_name, signal.symbol)
    return result


@router.post("/auto-paper")
async def auto_paper_order(
    payload: AutoPaperExecutionRequest,
    request: Request,
    engine: ExecutionEngine = Depends(get_engine),
    actor: User = Depends(require_trade_execute),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    symbol = payload.symbol.upper()
    from Backend.application.kill_switch import kill_switch_status

    if execution_mode == "live" and not _request_is_https(request) and not _allow_insecure_live():
        result = _paper_response(
            status_value="rejected",
            symbol=symbol,
            strategy=None,
            signal=None,
            reason="Live trading requires HTTPS.",
            execution_mode=execution_mode,
            extra={"allowed": False},
        )
        _audit_execution_result(db, request, actor, result)
        alert_execution_event(result)
        return result

    halt = kill_switch_status()
    if halt["active"]:
        result = _paper_response(
            status_value="rejected",
            symbol=symbol,
            strategy=None,
            signal=None,
            reason=f"KILL_SWITCH_ACTIVE: {halt.get('reason') or 'Trading halted'}",
            execution_mode=execution_mode,
            extra={"allowed": False, "kill_switch": halt},
        )
        _audit_execution_result(db, request, actor, result)
        alert_execution_event(result)
        return result
    write_audit_log(
        db,
        action="paper_auto_scan_triggered",
        actor=actor,
        target_type="symbol",
        target_id=symbol,
        request=request,
        metadata={"mode": execution_mode},
    )

    if execution_mode != "paper":
        return _paper_response(
            status_value="rejected",
            symbol=symbol,
            strategy=None,
            signal=None,
            reason="Auto execution is paper-only.",
            execution_mode=execution_mode,
        )

    candles_response = get_candles(symbol, interval=payload.interval, period=payload.period, limit=150)
    confirmation_response = get_candles(symbol, interval="5m", period=payload.period, limit=150)
    trend_response = get_candles(symbol, interval="15m", period=payload.period, limit=150)
    candles = _strategy_candles(candles_response)
    confirmation_candles = _strategy_candles(confirmation_response)
    trend_candles = _strategy_candles(trend_response)
    candle_validation = validate_live_candle(
        candles,
        interval=payload.interval,
        mode="paper",
        source=candles_response.get("source"),
        provider_fetched_at=candles_response.get("fetched_at"),
    )
    service = TradingService()
    strategies = payload.strategies or AUTO_SCAN_STRATEGIES
    strategy_diagnostics: dict[str, Any] = {}

    for strategy in strategies:
        try:
            raw_signals = service.run_strategy(
                strategy_name=strategy,
                data=candles,
                symbol=symbol,
                capital=payload.capital,
                risk_pct=payload.risk_pct,
                rr_ratio=payload.rr_ratio,
                params={"mtf_candles": confirmation_candles, "htf_candles": trend_candles},
            )
            observe_signal_generation(strategy, "success")
            validated_signals, data_source = validate_signals(
                raw_signals,
                symbol=symbol,
                candles=candles,
                candle_source=candles_response.get("source"),
            )
            diagnostics = diagnose_signal_run(
                raw_signals,
                symbol=symbol,
                candles=candles,
                candle_source=candles_response.get("source"),
            )
            strategy_diagnostics[strategy] = {
                "raw_signals": len(raw_signals),
                "validated_signals": len(validated_signals),
                "data_source": data_source,
                "market_status": candle_validation.market_status,
                "validation": candle_validation.model_dump(),
                "diagnostics": diagnostics,
            }
            if not validated_signals:
                continue

            selected = validated_signals[0]
            strategy_diagnostics[strategy]["selected_signal"] = serialize_signal(selected)
        except Exception as exc:
            observe_signal_generation(strategy, "error")
            strategy_diagnostics[strategy] = {
                "raw_signals": 0,
                "validated_signals": 0,
                "market_status": candle_validation.market_status,
                "validation": candle_validation.model_dump(),
                "diagnostics": [f"Strategy scan failed: {exc}"],
            }
            continue

        selected = validated_signals[0]
        strategy_diagnostics[strategy]["selected_signal"] = serialize_signal(selected)
        result = await _submit_paper_signal(
            selected,
            engine=engine,
            execution_mode=execution_mode,
            candles_1m=candles,
            candles_15m=trend_candles,
            strategy_diagnostics=strategy_diagnostics,
            broker_client=broker_client_for_mode(execution_mode),
            db=db,
            request=request,
            actor=actor,
        )
        if result.get("risk_decision"):
            _audit_risk_decision(
                db,
                request,
                actor,
                symbol=selected.symbol,
                strategy=selected.strategy_name,
                side=selected.side,
                risk_decision=result["risk_decision"],
            )
        _audit_execution_result(db, request, actor, result)
        alert_execution_event(result)
        return result

    result = _paper_response(
        status_value="no_trade",
        symbol=symbol,
        strategy=None,
        signal=None,
        reason="No validated signal found across auto-scan strategies.",
        execution_mode=execution_mode,
        strategy_diagnostics=strategy_diagnostics,
        extra={
            "candles_analyzed": len(candles),
            "strategies_checked": strategies,
            "validation": candle_validation.model_dump(),
        },
    )
    alert_execution_event(result)
    return result


@router.post("/auto-paper/jobs")
async def enqueue_auto_paper_order(
    payload: AutoPaperExecutionRequest,
    request: Request,
    actor: User = Depends(require_trade_execute),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    if execution_mode != "paper":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Auto-paper jobs are paper-only.")

    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    job = enqueue_job(
        "auto-paper",
        payload_data,
        metadata={
            "symbol": payload.symbol.upper(),
            "strategy": ",".join(payload.strategies or AUTO_SCAN_STRATEGIES),
            "interval": payload.interval,
            "period": payload.period,
        },
    )
    write_audit_log(
        db,
        action="trading_job_created",
        actor=actor,
        target_type="job",
        target_id=job["job_id"],
        request=request,
        metadata={"job_type": "auto-paper", "symbol": payload.symbol.upper(), "status": "queued"},
    )
    return job


@router.post("/order")
async def place_order(
    signal: StrategySignal,
    request: Request,
    engine: ExecutionEngine = Depends(get_engine),
    actor: User = Depends(require_trade_execute),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    write_audit_log(
        db,
        action="execution_triggered",
        actor=actor,
        target_type="symbol",
        target_id=signal.symbol,
        request=request,
        metadata={"mode": execution_mode, "strategy": signal.strategy_name},
    )

    candles_1m = latest_candles(signal.symbol, "1m", 100)
    if not candles_1m:
        try:
            candles_1m = _strategy_candles(get_candles(signal.symbol, interval="1m", period="1d", limit=100))
        except Exception:
            candles_1m = []

    if execution_mode == "live" and not _request_is_https(request) and not _allow_insecure_live():
        result = _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason="Live trading requires HTTPS.",
            execution_mode=execution_mode,
            extra={
                "allowed": False,
                "risk_amount": 0.0,
                "max_allowed_risk": 0.0,
                "live_guardrail": "failed",
            },
        )
        write_audit_log(
            db,
            action="execution_blocked",
            actor=actor,
            target_type="symbol",
            target_id=signal.symbol,
            request=request,
            metadata={
                "reason": "Live trading requires HTTPS.",
                "status": "rejected",
                "strategy": signal.strategy_name,
                "side": signal.side,
                "live_guardrail": "failed",
            },
        )
        alert_execution_event(result)
        return result

    qualification = _execution_qualification(
        signal,
        candles_1m=candles_1m,
        candles_15m=candles_15m,
        execution_mode=execution_mode,
    )
    if qualification is not None and not qualification.allowed:
        result = _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=f"TQE_REJECTED: {qualification.reason}",
            execution_mode=execution_mode,
            extra={"allowed": False, **_tqe_response_fields(qualification)},
        )
        _audit_execution_result(db, request, actor, result)
        alert_execution_event(result)
        return result

    risk_decision = validate_order_risk(signal, execution_mode=execution_mode, candles_1m=candles_1m)
    _audit_risk_decision(
        db,
        request,
        actor,
        symbol=signal.symbol,
        strategy=signal.strategy_name,
        side=signal.side,
        risk_decision=risk_decision,
    )
    if not risk_decision.allowed:
        result = _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=risk_decision.reason,
            execution_mode=execution_mode,
            extra=_risk_response_fields(risk_decision),
        )
        _audit_execution_result(db, request, actor, result)
        alert_execution_event(result)
        return result

    if execution_mode == "live":
        settings = get_settings()
        guardrail_reason = _live_guardrail_failure(
            request=request,
            actor=actor,
            settings=settings,
            candles_1m=candles_1m,
            risk_decision=risk_decision,
        )
        if guardrail_reason:
            result = _reject_live_guardrail(
                db=db,
                request=request,
                actor=actor,
                signal=signal,
                reason=guardrail_reason,
                execution_mode=execution_mode,
                risk_decision=risk_decision,
            )
            alert_execution_event(result)
            return result
        if not settings.live_trading_enabled or not settings.broker_live_enabled:
            write_audit_log(
                db,
                action="execution_blocked",
                actor=actor,
                target_type="symbol",
                target_id=signal.symbol,
                request=request,
                metadata={"reason": "live_trading_disabled"},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Live trading is disabled. Set BROKER_LIVE_ENABLED=true and enable live trading.")
        if not settings.broker_configured:
            write_audit_log(
                db,
                action="execution_blocked",
                actor=actor,
                target_type="symbol",
                target_id=signal.symbol,
                request=request,
                metadata={"reason": "broker_not_configured"},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Live trading requires broker credentials.")
        order = engine.order_from_signal(signal)
        lifecycle_order = _create_lifecycle_order(order, db=db, request=request, actor=actor)
        lifecycle_order = _transition_lifecycle_order(
            lifecycle_order,
            "risk_approved",
            db=db,
            request=request,
            actor=actor,
            reason="Risk engine and live guardrails approved order.",
        )
        try:
            broker_client = broker_client_for_mode(execution_mode)
            lifecycle_order = _transition_lifecycle_order(
                lifecycle_order,
                "broker_submitted",
                db=db,
                request=request,
                actor=actor,
                reason="Submitted to broker adapter.",
            )
            broker_order = await broker_client.place_order(order)
            lifecycle_order = _transition_lifecycle_order(
                lifecycle_order,
                "broker_submitted",
                db=db,
                request=request,
                actor=actor,
                reason="Broker accepted submission.",
                broker_order_id=broker_order.broker_order_id,
                entry_price=broker_order.price,
                broker_response=broker_order.to_dict(),
            )
            broker_status = await broker_client.get_order_status(broker_order.broker_order_id)
        except Exception as exc:
            lifecycle_order = _transition_lifecycle_order(
                lifecycle_order,
                "failed",
                db=db,
                request=request,
                actor=actor,
                reason=f"BROKER_FAILURE: {exc}",
            )
            result = _paper_response(
                status_value="rejected",
                symbol=signal.symbol,
                strategy=signal.strategy_name,
                signal=signal,
                reason=f"BROKER_FAILURE: {exc}",
                execution_mode=execution_mode,
                extra={
                    **_risk_response_fields(risk_decision),
                    **(_tqe_response_fields(qualification) if qualification is not None else {}),
                    "broker_confirmed": False,
                },
            )
            _audit_execution_result(db, request, actor, result)
            alert_execution_event(result)
            return result
        if not broker_status.confirmed or broker_status.status in {"rejected", "failed", "not_found"}:
            mapped_status = broker_status_to_order_status(broker_status.status, confirmed=broker_status.confirmed)
            lifecycle_order = _transition_lifecycle_order(
                lifecycle_order,
                mapped_status if mapped_status in {"rejected", "failed", "cancelled"} else "rejected",
                db=db,
                request=request,
                actor=actor,
                reason=f"BROKER_NOT_CONFIRMED: {broker_status.status}",
                broker_order_id=broker_status.broker_order_id,
                entry_price=broker_status.price,
                broker_response=broker_status.to_dict(),
            )
            result = _paper_response(
                status_value="rejected",
                symbol=signal.symbol,
                strategy=signal.strategy_name,
                signal=signal,
                reason=f"BROKER_NOT_CONFIRMED: {broker_status.status}",
                execution_mode=execution_mode,
                extra={
                    **_risk_response_fields(risk_decision),
                    **(_tqe_response_fields(qualification) if qualification is not None else {}),
                    "broker_order_id": broker_status.broker_order_id,
                    "broker_status": broker_status.status,
                    "broker_confirmed": False,
                    "broker_order": broker_status.to_dict(),
                    "raw_safe_broker_response": broker_status.metadata.get("raw_safe"),
                },
            )
            _audit_execution_result(db, request, actor, result)
            alert_execution_event(result)
            return result
        order_status = broker_status_to_order_status(broker_status.status, confirmed=broker_status.confirmed)
        lifecycle_order = _transition_lifecycle_order(
            lifecycle_order,
            order_status,
            db=db,
            request=request,
            actor=actor,
            reason=f"Broker status confirmed: {broker_status.status}",
            broker_order_id=broker_status.broker_order_id,
            entry_price=broker_status.price or signal.entry_price,
            broker_response=broker_status.to_dict(),
        )
        result = _paper_response(
            status_value="live_order_submitted",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason="OK",
            execution_mode=execution_mode,
            extra={
                **_risk_response_fields(risk_decision),
                **(_tqe_response_fields(qualification) if qualification is not None else {}),
                "broker_order_id": broker_status.broker_order_id,
                "local_order_id": lifecycle_order.get("local_order_id") if lifecycle_order else None,
                "broker_status": broker_status.status,
                "broker_confirmed": True,
                "broker_order": broker_status.to_dict(),
                "raw_safe_broker_response": broker_status.metadata.get("raw_safe"),
            },
        )
        create_paper_trade(
            {
                "strategy": signal.strategy_name,
                "symbol": signal.symbol,
                "side": signal.side,
                "entry": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "target": signal.target_price,
                "status": "live_order_submitted",
                "pnl": 0.0,
                "reason": "OK",
                "broker_order_id": broker_status.broker_order_id,
                "broker_status": broker_status.status,
                "raw_safe_broker_response": broker_status.metadata.get("raw_safe"),
                "signal_time": signal.signal_time.isoformat(),
            }
        )
        if should_create_position(order_status):
            create_open_position(
                {
                    "broker_order_id": broker_status.broker_order_id,
                    "symbol": signal.symbol,
                    "side": signal.side,
                    "quantity": requested_quantity(signal),
                    "entry_price": signal.entry_price,
                    "stop_loss": signal.stop_loss,
                    "target": signal.target_price,
                    "current_price": broker_status.price or signal.entry_price,
                    "opened_at": signal.signal_time.isoformat(),
                }
            )
        _audit_execution_result(db, request, actor, result)
        alert_execution_event(result)
        return result

    result = await _submit_paper_signal(
        signal,
        engine=engine,
        execution_mode=execution_mode,
        candles_1m=candles_1m,
        candles_15m=candles_15m,
        db=db,
        request=request,
        actor=actor,
    )
    _audit_execution_result(db, request, actor, result)
    alert_execution_event(result)
    return result
