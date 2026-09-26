from __future__ import annotations
from typing import Any


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
from Backend.application.execution import execution_pipeline as _execution_pipeline
from Backend.application.execution import execution_guardrails as _execution_guardrails
from Backend.application.execution.execution_guardrails import (
    _request_is_https,
    _allow_insecure_live,
)
from Backend.application.execution.broker_execution import _broker_session_valid
from Backend.application.execution.execution_validator import market_aligned
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
from Backend.application.broker_circuit_breaker import  record_broker_failure
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
from Backend.application.execution.execution_utils import (
    _trade_shape_reason,
    _tqe_response_fields,
    _risk_response_fields,
)
import logging

def _market_aligned(signal):
    aligned, _reason = market_aligned(signal, get_price)
    return aligned


async def _submit_paper_signal(*args, **kwargs):
    """Compatibility boundary for execution API tests and callers."""
    return await _execution_pipeline._submit_paper_signal(*args, **kwargs)


def _live_guardrail_failure(*, request, actor, settings, candles_1m, risk_decision, signal=None):
    """Compatibility boundary for execution API tests and callers."""
    original_kill_switch_status = _execution_guardrails.kill_switch_status
    original_validate_live_candle = _execution_guardrails.validate_live_candle
    original_broker_session_valid = _execution_guardrails._broker_session_valid

    try:
        _execution_guardrails.kill_switch_status = kill_switch_status
        _execution_guardrails.validate_live_candle = validate_live_candle
        _execution_guardrails._broker_session_valid = _broker_session_valid
        return _execution_guardrails._live_guardrail_failure(
            request=request,
            actor=actor,
            settings=settings,
            candles_1m=candles_1m,
            risk_decision=risk_decision,
            signal=signal,
        )
    finally:
        _execution_guardrails.kill_switch_status = original_kill_switch_status
        _execution_guardrails.validate_live_candle = original_validate_live_candle
        _execution_guardrails._broker_session_valid = original_broker_session_valid


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
    

class AutoPaperExecutionRequest(BaseModel):
    """
    Request model for automated paper trading.
    """

    symbol: str = Field(
        default="NIFTY",
        min_length=1,
        max_length=30,
        description="Trading symbol",
    )

    interval: Literal[
        "1m",
        "3m",
        "5m",
        "10m",
        "15m",
        "30m",
        "1h",
        "1d",
    ] = Field(
        default="1m",
        description="Candle interval",
    )

    period: Literal[
        "1d",
        "5d",
        "1mo",
        "3mo",
        "6mo",
        "1y",
    ] = Field(
        default="1d",
        description="Historical period",
    )

    capital: float = Field(
        default=100000.0,
        gt=0,
        le=100000000,
        description="Trading capital",
    )

    risk_pct: float = Field(
        default=2.0,
        gt=0,
        le=10,
        description="Risk percentage per trade",
    )

    rr_ratio: float = Field(
        default=2.0,
        gt=0,
        le=10,
        description="Risk-reward ratio",
    )

    strategies: list[str] = Field(
        default_factory=list,
        description="Strategies to scan",
    )

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("Symbol cannot be empty.")

        return value

    @field_validator("strategies")
    @classmethod
    def validate_strategies(cls, strategies: list[str]) -> list[str]:
        return [strategy.strip().lower() for strategy in strategies if strategy.strip()]





def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()

    return model.dict()

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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "subscription_required", "feature": "paper_trade.automated", "current_plan": access.snapshot["plan_code"].upper(), "message": "Automated paper trading requires a Pro or Premium plan."})
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

    candles_response = market_service.get_candles(symbol, interval=payload.interval, period=payload.period, limit=150)
    confirmation_response = market_service.get_candles(symbol, interval="5m", period=payload.period, limit=150)
    trend_response = market_service.get_candles(symbol, interval="15m", period=payload.period, limit=150)
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
        scan_market_status = str(getattr(candle_validation, "market_status", "LIVE MARKET"))
        if not candle_validation.valid_for_execution or scan_market_status.upper() != "LIVE MARKET":
            result = _paper_response(
                status_value="rejected",
                symbol=symbol,
                strategy=selected.strategy_name,
                signal=selected,
                reason=f"MARKET_NOT_LIVE_FOR_EXECUTION: {scan_market_status}",
                execution_mode=execution_mode,
                strategy_diagnostics=strategy_diagnostics,
                extra={"validation": candle_validation.model_dump()},
            )
            _audit_execution_result(db, request, actor, result)
            alert_execution_event(result)
            return result
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
    access: SubscriptionAccess = Depends(subscription_access),
    execution_mode: str = Depends(_execution_mode),
    engine: ExecutionEngine = Depends(get_engine),
):
    if not access.can("paper_trade.automated"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "subscription_required",
                "feature": "paper_trade.automated",
                "current_plan": access.snapshot["plan_code"].upper(),
                "message": "Automated paper trading requires a Pro or Premium plan.",
            },
        )

    if execution_mode != "paper":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auto-paper jobs are paper-only.",
        )

    return {
    "status": "accepted",
    "message": "Auto paper job queued",
    "symbol": payload.symbol if hasattr(payload, "symbol") else None,
}


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
    logging.getLogger(__name__).info(
        "POST /order received: symbol=%s strategy=%s mode=%s",
        signal.symbol,
        signal.strategy_name,
        execution_mode,
    )

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
    