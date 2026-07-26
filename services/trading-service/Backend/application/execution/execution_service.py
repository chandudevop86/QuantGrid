from typing import Any
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
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
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Final


market_service = MarketDataService()

def _audit_execution_result(
    db: Session,
    request: Request,
    actor: User,
    result: dict[str, Any],
) -> None:
    """
    Audit the final execution result.
    """

    status = str(result.get("status", ""))

    submitted = status in {
        "paper_order_submitted",
        "live_order_submitted",
    }

    action = (
        "live_order_submitted"
        if status == "live_order_submitted"
        else (
            "paper_order_submitted"
            if status == "paper_order_submitted"
            else "execution_blocked"
        )
    )

    metadata: dict[str, Any] = {
        "status": "submitted" if submitted else "rejected",
        "strategy": result.get("strategy"),
        "side": result.get("signal"),
        "reason": result.get("reason"),
        "execution_mode": result.get("execution_mode"),
        "risk_decision": result.get("risk_decision"),
        "trade_qualification": result.get("trade_qualification"),
        "quality_grade": result.get("quality_grade"),
        "tqe_score": result.get("tqe_score"),
        "local_order_id": result.get("local_order_id"),
        "broker_order_id": result.get("broker_order_id"),
        "broker_status": result.get("broker_status"),
        "trailing_stop_loss": result.get("trailing_stop_loss"),
        "trailing_stop_pct": result.get("trailing_stop_pct"),
        "broker_order": result.get("broker_order"),
        "raw_safe_broker_response": result.get("raw_safe_broker_response"),
    }

    # Remove empty values to keep audit logs compact.
    metadata = {
        key: value
        for key, value in metadata.items()
        if value is not None
    }

    write_audit_log(
        db=db,
        action=action,
        actor=actor,
        target_type="symbol",
        target_id=result.get("symbol"),
        request=request,
        metadata=metadata,
    )


def _audit_order_transition(
    db: Session | None,
    request: Request | None,
    actor: User | None,
    order: dict[str, Any],
    previous_status: str,
    broker_response: dict[str, Any] | None = None,
) -> None:
    """
    Audit an order lifecycle status transition.
    """

    if db is None or request is None or actor is None:
        return

    metadata: dict[str, Any] = {
        "from_status": previous_status,
        "to_status": order.get("status"),
        "status_reason": order.get("status_reason"),
        "broker_order_id": order.get("broker_order_id"),
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "quantity": order.get("quantity"),
        "entry_price": order.get("entry_price"),
        "stop_loss": order.get("stop_loss"),
        "target": order.get("target"),
        "trailing_stop_loss": order.get("trailing_stop_loss"),
        "trailing_stop_pct": order.get("trailing_stop_pct"),
        "broker_response": broker_response,
    }

    # Remove empty values
    metadata = {
        key: value
        for key, value in metadata.items()
        if value is not None
    }

    write_audit_log(
        db=db,
        action="order_status_transition",
        actor=actor,
        target_type="order",
        target_id=order.get("local_order_id"),
        request=request,
        metadata=metadata,
    )




def _execution_qualification(
    signal: StrategySignal,
    *,
    candles_1m: list[dict[str, Any]],
    candles_15m: list[dict[str, Any]] | None,
    execution_mode: str,
) -> TradeQualification | None:
    """
    Run the Trade Qualification Engine (TQE) and enrich the signal metadata.
    """

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

    signal.metadata.update(
        {
            "trade_qualification": qualification.to_dict(),
            "tqe_score": qualification.score,
            "quality_grade": qualification.quality_grade,
            "market_context": qualification.market_context,
            "volume_status": qualification.volume_status,
            "volatility_status": qualification.volatility_status,
        }
    )

    return qualification




