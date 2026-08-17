from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from Backend.application.execution.audit_manager import (
    _audit_risk_decision,
    _serialize_risk_decision,
)
from Backend.application.execution.execution_response import (
    _paper_response,
    _risk_response_fields,
)
from Backend.domain.models.signal import StrategySignal
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User


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
    """
    Reject a live order because a live-trading guardrail failed.

    Order is NOT submitted to the broker.
    """

    # ---------------------------------------------------------
    # Audit risk decision first
    # ---------------------------------------------------------

    _audit_risk_decision(
        db=db,
        request=request,
        actor=actor,
        symbol=signal.symbol,
        strategy=signal.strategy_name,
        side=signal.side,
        risk_decision=risk_decision,
    )

    # ---------------------------------------------------------
    # Build rejection response
    # ---------------------------------------------------------

    result = _paper_response(
        status_value="rejected",
        symbol=signal.symbol,
        strategy=signal.strategy_name,
        signal=signal,
        reason=reason,
        execution_mode=execution_mode,
        extra={
            **_risk_response_fields(
                risk_decision
            ),
            "live_guardrail": "failed",
        },
    )

    # ---------------------------------------------------------
    # Execution-block audit
    # ---------------------------------------------------------

    metadata = {
        key: value
        for key, value in {
            "status": "rejected",
            "reason": reason,
            "strategy": signal.strategy_name,
            "side": signal.side,
            "execution_mode": execution_mode,
            "risk_decision": result.get(
                "risk_decision"
            ),
            "live_guardrail": "failed",
        }.items()
        if value is not None
    }

    write_audit_log(
        db=db,
        action="execution_blocked",
        actor=actor,
        target_type="symbol",
        target_id=signal.symbol,
        request=request,
        metadata=metadata,
    )

    return result