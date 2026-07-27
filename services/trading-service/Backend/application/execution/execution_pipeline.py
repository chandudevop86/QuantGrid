from typing import Any, Final, Literal
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from Backend.application.candle_validation import validate_live_candle
from Backend.application.broker_circuit_breaker import broker_circuit_status, record_broker_failure
from Backend.application.dto import serialize_signal
from Backend.application.job_queue import enqueue_job
from Backend.core.config import get_settings
from Backend.core.database import get_db
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
from Backend.application.market_data_store import latest_candles
from Backend.application.kill_switch import kill_switch_status
from Backend.application.monitoring import observe_paper_order, observe_rejected_order, observe_signal_generation
from Backend.presentation.api.roles import current_user, require_trade_execute
from Backend.application.market_data_service import MarketDataService
from Backend.presentation.api.market_api import get_price
from Backend.config import Provider
from pydantic import BaseModel, Field, field_validator, model_validator
from Backend.application.execution.execution_response import _paper_response,_risk_response_fields
from Backend.application.execution.lifecycle_manager import _create_lifecycle_order
from Backend.presentation.api.execution import _tqe_response_fields,_transition_lifecycle_order,_trade_shape_reason
from Backend.application.execution.execution_validator import market_aligned


def _load_execution_candles(
    symbol: str,
    *,
    candles_1m: list[dict[str, Any]] | None = None,
    candles_15m: list[dict[str, Any]] | None = None,
) -> tuple[
    list[dict[str, Any]] | None,
    list[dict[str, Any]] | None,
]:
    """
    Load execution candles.
    Uses provided candles first, otherwise fetches latest cached candles.
    """

    if candles_1m is None:
        try:
            candles_1m = latest_candles(
                symbol=symbol,
                timeframe="1m",
            )
        except Exception:
            candles_1m = None

    if candles_15m is None:
        try:
            candles_15m = latest_candles(
                symbol=symbol,
                timeframe="15m",
            )
        except Exception:
            candles_15m = None

    return candles_1m, candles_15m
async def _submit_paper_signal(
    signal: StrategySignal,
    *,
    engine: ExecutionEngine,
    execution_mode: str,
    candles_1m: list[dict[str, Any]] | None = None,
    candles_15m: list[dict[str, Any]] | None = None,
    candles_by_timeframe: dict[str, list[dict[str, Any]]] | None = None,    strategy_diagnostics: dict[str, Any] | None = None,
    broker_client: BrokerClient | None = None,
    db: Session | None = None,
    request: Request | None = None,
    actor: User | None = None,
) -> dict[str, Any]:
    if execution_mode != "paper":
        if candles_by_timeframe:
            candles_1m = candles_by_timeframe.get("1m") or candles_1m
            candles_15m = candles_by_timeframe.get("15m") or candles_15m
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
    candles_1m, candles_15m = _load_execution_candles(
    signal.symbol,
    candles_1m=candles_1m,
    candles_15m=candles_15m,
    )
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
    metadata = getattr(signal, "metadata", {}) or {}    
    candle_validation = validate_live_candle(candles_1m, interval="1m", mode="paper")
    market_status = str(getattr(candle_validation, "market_status", "LIVE MARKET"))
    if not candle_validation.valid_for_execution or market_status.upper() != "LIVE MARKET":
        reason = f"MARKET_NOT_LIVE_FOR_EXECUTION: {market_status}"
        observe_rejected_order(reason, execution_mode)
        return _paper_response(
            status_value="rejected",
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            signal=signal,
            reason=reason,
            execution_mode=execution_mode,
            strategy_diagnostics=strategy_diagnostics,
            extra={**_risk_response_fields(risk_decision), "allowed": False, "validation":candle_validation.dict()},
        )
    candles_by_timeframe = {
    "1m": candles_1m,
    "15m": candles_15m or [],
}   
    decision = decide_signal(signal, candles_1m=candles_1m, candles_by_timeframe=candles_by_timeframe)
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

    if not market_aligned(signal):
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
    try:
        lifecycle_order = _create_lifecycle_order(order, signal=signal, execution_mode=execution_mode, db=db, request=request, actor=actor)
    except ValueError as exc:
        if str(exc).startswith("DUPLICATE_ACTIVE_ORDER"):
            observe_rejected_order("duplicate_active_order", execution_mode)
            return _paper_response(
                status_value="rejected",
                symbol=signal.symbol,
                strategy=signal.strategy_name,
                signal=signal,
                reason=str(exc),
                execution_mode=execution_mode,
                strategy_diagnostics=strategy_diagnostics,
                extra={**_risk_response_fields(risk_decision), "broker_confirmed": False},
            )
        raise
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
        oms_result = await OrderManagementService(broker_client).submit_order(
            order,
            signal,
            {
                "local_order_id": lifecycle_order["local_order_id"] if lifecycle_order else None,
                "prevalidated_risk": {
                    "allowed": risk_decision.allowed,
                    "reasons": [risk_decision.reason],
                    "risk_score": risk_decision.details.get("risk_engine", {}).get("risk_score", 100),
                    "blocked_by": risk_decision.details.get("risk_engine", {}).get("blocked_by", []),
                    "warnings": risk_decision.details.get("risk_engine", {}).get("warnings", []),
                },
            },
        )
        if not oms_result.accepted:
            lifecycle_order = _transition_lifecycle_order(
                lifecycle_order,
                "rejected" if oms_result.status == "rejected" else "failed",
                db=db,
                request=request,
                actor=actor,
                reason=f"OMS_{oms_result.status.upper()}: {'; '.join(oms_result.reasons)}",
                broker_order_id=oms_result.broker_order_id,
                broker_status=oms_result.status,
                broker_response=oms_result.to_dict(),
            )
            observe_rejected_order(f"oms_{oms_result.status}", execution_mode)
            return _paper_response(
                status_value="rejected",
                symbol=signal.symbol,
                strategy=signal.strategy_name,
                signal=signal,
                reason=f"OMS_{oms_result.status.upper()}: {'; '.join(oms_result.reasons)}",
                execution_mode=execution_mode,
                strategy_diagnostics=strategy_diagnostics,
                extra={**_risk_response_fields(risk_decision), "oms": oms_result.to_dict(), "broker_confirmed": False},
            )
        lifecycle_order = _transition_lifecycle_order(
            lifecycle_order,
            "broker_submitted",
            db=db,
            request=request,
            actor=actor,
            reason="Broker accepted submission.",
            broker_order_id=oms_result.broker_order_id,
            broker_status=oms_result.status,
            broker_response=oms_result.to_dict(),
        )
        broker_status = await broker_client.get_order_status(str(oms_result.broker_order_id))
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
            broker_status=broker_status.status,
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
                "raw_safe_broker_response": (broker_status.metadata or {}).get("raw_safe"),
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
        broker_status=broker_status.status,
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
            "raw_safe_broker_response": (broker_status.metadata or {}).get("raw_safe")
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
            "status": "paper_order_submitted",
            "pnl": 0.0,
            "reason": "OK",
            "broker_order_id": broker_status.broker_order_id,
            "score": decision.score,
            "tqe_score": qualification.score if qualification is not None else metadata.get("tqe_score", 0),
            "quality_grade": qualification.quality_grade if qualification is not None else metadata.get("quality_grade"),
            "regime": decision.regime,
            "signal_time": signal.signal_time.isoformat(),
            "broker_status": broker_status.status,
            "raw_safe_broker_response": (broker_status.metadata or {}).get("raw_safe")
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
    observe_paper_order("paper_order_submitted", signal.strategy_name, signal.symbol)
    return result
