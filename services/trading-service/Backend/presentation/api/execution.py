from __future__ import annotations
from typing import Any
import os

from sqlalchemy.orm import Session
from Backend.application.market_data_service import (
    MarketDataService,
    _strategy_candles,
)
from Backend.application.execution.execution_service import (
    
    _audit_execution_result,
    _execution_qualification,
)
from Backend.application.execution.execution_response import _paper_response
from Backend.application.execution.execution_pipeline import _submit_paper_signal
from Backend.application.execution.execution_guardrails import (
    _live_guardrail_failure,
    _request_is_https,
    _allow_insecure_live,
)
from Backend.application.execution.lifecycle_manager import (
    _create_lifecycle_order,
    _transition_lifecycle_order,
)
from Backend.application.execution.audit_manager import (
    _audit_risk_decision,
)
from Backend.application.subscriptions import (
    SubscriptionAccess,
    subscription_access,
)
from Backend.application.execution.audit_manager import (
    _reject_live_guardrail,
)
from Backend.core.database import get_db
from Backend.domain.engine.order_factory import ExecutionEngine
from Backend.domain.models.signal import StrategySignal
from Backend.domain.security.models import User
from Backend.presentation.api.roles import require_trade_execute
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
#from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from Backend.application.candle_validation import validate_live_candle
from Backend.application.broker_circuit_breaker import broker_circuit_status, record_broker_failure
from Backend.application.dto import serialize_signal
from Backend.application.job_queue import enqueue_job
from Backend.core.config import get_settings
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
from Backend.application.trade_qualification_engine import TradeQualificationEngine, TradeQualification
from Backend.application.trading_service import TradingService
from Backend.application.trading_engine_upgrade import (
    scale_position,
    submit_paper_basket,
    trading_engine_dashboard,
)
from Backend.application.subscriptions import SubscriptionAccess, subscription_access
from Backend.domain.execution_constraints import (
    apply_order_constraints,
    requested_quantity,
    validate_execution_constraints,
)

from Backend.domain.security.audit import write_audit_log
from Backend.infrastructure.broker.broker_client import BrokerClient, broker_client_for_mode
from Backend.infrastructure.broker.dhan_status import check_dhan_profile
from Backend.application.market_data_store import latest_candles
from Backend.application.kill_switch import kill_switch_status
from Backend.application.monitoring import observe_paper_order, observe_rejected_order, observe_signal_generation
from Backend.presentation.api.roles import current_user, require_trade_execute
from Backend.application.market_data_service import MarketDataService
from Backend.presentation.api.market_api import get_price
from Backend.config import Provider
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Final

def _trade_shape_reason(signal: StrategySignal) -> str | None:
    """
    Validate trade shape.
    Returns rejection reason only when invalid.
    """

    entry = float(signal.entry_price)
    stop = float(signal.stop_loss)
    target = float(signal.target_price)

    side = str(signal.side).upper()

    if entry <= 0 or stop <= 0 or target <= 0:
        return "INVALID_PRICE_VALUES"

    risk = abs(entry - stop)
    reward = abs(target - entry)

    if risk <= 0:
        return "INVALID_STOP_LOSS"

    rr = reward / risk

    if rr < 1:
        return f"INVALID_RISK_REWARD:{rr:.2f}"

    if side == "BUY":
        if stop >= entry:
            return "BUY_STOP_MUST_BE_BELOW_ENTRY"

        if target <= entry:
            return "BUY_TARGET_MUST_BE_ABOVE_ENTRY"

    elif side == "SELL":
        if stop <= entry:
            return "SELL_STOP_MUST_BE_ABOVE_ENTRY"

        if target >= entry:
            return "SELL_TARGET_MUST_BE_BELOW_ENTRY"

    else:
        return "INVALID_SIDE"

    return None
def _tqe_response_fields(
    qualification=None,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build Trade Quality Evaluation response fields.
    Supports TradeQualification object or dict.
    """

    if qualification is not None and hasattr(qualification, "to_dict"):
        qualification = qualification.to_dict()

    qualification = qualification or {}
    diagnostics = diagnostics or {}

    return {
        "trade_quality": {
            "qualified": qualification.get(
                "allowed",
                qualification.get("qualified", False),
            ),
            "risk_reward": qualification.get(
                "rr",
                qualification.get("risk_reward"),
            ),
            "checks": qualification,
        },
        "strategy_diagnostics": diagnostics,
    }
def _risk_response_fields(
    *,
    signal: StrategySignal,
    qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build risk evaluation fields for execution response.
    """

    qualification = qualification or {}

    risk_amount = abs(
        float(signal.entry_price) - float(signal.stop_loss)
    )

    reward_amount = abs(
        float(signal.target_price) - float(signal.entry_price)
    )

    risk_reward = (
        round(reward_amount / risk_amount, 2)
        if risk_amount > 0
        else 0.0
    )

    return {
        "risk": {
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "target_price": signal.target_price,
            "risk_amount": round(risk_amount, 2),
            "reward_amount": round(reward_amount, 2),
            "risk_reward": risk_reward,
            "passed": qualification.get(
                "risk_reward_passed",
                risk_reward >= 1.5,
            ),
        }
    }
router = APIRouter()
market_service = MarketDataService()
AUTO_SCAN_STRATEGIES = ["amd", "breakout", "btst", "cbt", "crt_tbs", "mean_reversion", "mtf", "mtfa", "supply_demand"]
#service = ExecutionService()

def get_engine():
    return ExecutionEngine()
def _execution_mode(x_quantgrid_mode: str = Header(default="paper", alias="X-QuantGrid-Mode")) -> str:
    mode = x_quantgrid_mode.strip().lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid execution mode.")
    return mode
    

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
    required_feature = "live_trade.execute" if execution_mode == "live" else "paper_trade.manual"
    if not access.can(required_feature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "subscription_required", "feature": required_feature, "current_plan": access.snapshot["plan_code"].upper(), "message": "Your active subscription does not include this execution mode."})
    write_audit_log(
        db,
        action="execution_triggered",
        actor=actor,
        target_type="symbol",
        target_id=signal.symbol,
        request=request,
        metadata={"mode": execution_mode, "strategy": signal.strategy_name},
    )

    if execution_mode == "live":
        settings = get_settings()
        if not getattr(settings, "live_trading_enabled", False):
            write_audit_log(
                db,
                action="execution_blocked",
                actor=actor,
                target_type="symbol",
                target_id=signal.symbol,
                request=request,
                metadata={"reason": "live_trading_disabled"},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Live trading is disabled. Paper trading only.")
        if not getattr(settings, "broker_configured", False):
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

    candles_1m = latest_candles(signal.symbol, "1m", 100)
    if not candles_1m:
        try:
            candles_1m = _strategy_candles(market_service.get_candles(signal.symbol, interval="1m", period="1d", limit=100))
        except Exception:
            candles_1m = []
    candles_15m = latest_candles(signal.symbol, "15m", 100)
    if not candles_15m:
        try:
            candles_15m = _strategy_candles(market_service.get_candles(signal.symbol, interval="15m", period="1d", limit=100))
        except Exception:
            candles_15m = []

    shape_reason = _trade_shape_reason(signal)
    if shape_reason:
        result = _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=shape_reason,
            execution_mode=execution_mode,
            extra={"allowed": False},
        )
        _audit_execution_result(db, request, actor, result)
        alert_execution_event(result)
        return result

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
    candles_by_timeframe = {
    "1m": candles_1m,
    "15m": candles_15m,
}
    qualification = _execution_qualification(
    signal,
    candles_1m=candles_1m,
    candles_15m=candles_15m,
    execution_mode=execution_mode,
    )

    print(
        "TQE RESULT:",
        qualification.to_dict() if qualification else None,
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
            signal=signal,
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
        lifecycle_order = _create_lifecycle_order(order, execution_mode=execution_mode, db=db, request=request, actor=actor)
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
                broker_status=broker_order.status,
                entry_price=broker_order.price,
                broker_response=broker_order.to_dict(),
            )
            broker_status = await broker_client.get_order_status(broker_order.broker_order_id)
        except Exception as exc:
            record_broker_failure(
                reason=str(exc),
                db=db,
                actor=actor,
                request=request,
                metadata={"symbol": signal.symbol, "side": signal.side, "phase": "broker_submit"},
            )
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
            record_broker_failure(
                reason=f"BROKER_NOT_CONFIRMED: {broker_status.status}",
                db=db,
                actor=actor,
                request=request,
                metadata={
                    "symbol": signal.symbol,
                    "side": signal.side,
                    "phase": "broker_confirm",
                    "broker_order_id": broker_status.broker_order_id,
                    "broker_status": broker_status.status,
                },
            )
            mapped_status = broker_status_to_order_status(broker_status.status, confirmed=broker_status.confirmed)
            lifecycle_order = _transition_lifecycle_order(
                lifecycle_order,
                mapped_status if mapped_status in {"rejected", "failed", "cancelled"} else "rejected",
                db=db,
                request=request,
                actor=actor,
                reason=f"BROKER_NOT_CONFIRMED: {broker_status.status}",
                broker_order_id=broker_status.broker_order_id,
                broker_status=broker_status.status,
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
            broker_status=broker_status.status,
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
                "trailing_stop_loss": signal.trailing_stop_loss,
                "trailing_stop_pct": signal.trailing_stop_pct,
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
                    "trailing_stop_loss": signal.trailing_stop_loss,
                    "trailing_stop_pct": signal.trailing_stop_pct,
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
        candles_by_timeframe=candles_by_timeframe,
        db=db,
        request=request,
        actor=actor,
    )
    _audit_execution_result(db, request, actor, result)
    alert_execution_event(result)
    return result
    