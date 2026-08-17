from __future__ import annotations

import os
from typing import Any, Final, Literal

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from Backend.application.audit_manager import _audit_order_transition
from Backend.application.broker_circuit_breaker import (
    broker_circuit_status,
    record_broker_failure,
)
from Backend.application.candle_validation import validate_live_candle
from Backend.application.dto import serialize_signal
from Backend.application.execution.audit_manager import (
    _audit_execution_result,
    _audit_order_transition,
    _audit_risk_decision,
)
from Backend.application.execution.risk_audit import (
    _reject_live_guardrail,
)
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
from Backend.application.risk_gate import (
    evaluate_risk_gate,
    validate_order_risk,
)
from Backend.application.signal_quality import decide_signal
from Backend.application.signal_validation import (
    diagnose_signal_run,
    validate_signals,
)
from Backend.application.subscriptions import (
    SubscriptionAccess,
    subscription_access,
)
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

from Backend.infrastructure.broker.broker_client import (
    BrokerClient,
    broker_client_for_mode,
)
from Backend.infrastructure.broker.dhan_status import check_dhan_profile

from Backend.presentation.api.market_api import get_price
from Backend.presentation.api.roles import (
    current_user,
    require_trade_execute,
)


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




