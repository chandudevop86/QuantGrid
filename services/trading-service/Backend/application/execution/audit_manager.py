from typing import Any
from fastapi import Request
from sqlalchemy.orm import Session
from Backend.domain.models.signal import StrategySignal
from Backend.domain.security.models import User

from Backend.application.execution.execution_response import _paper_response, _risk_response_fields
from Backend.domain.security.audit import write_audit_log

    # ---------------------------------------------------------
    # Risk Decision Serializer
    # ---------------------------------------------------------

def _serialize_risk_decision(
        risk_decision: Any,
    ) -> dict[str, Any]:
        """
Convert risk decision object into audit-safe dictionary.
Supports:
- Pydantic v2 models
- custom objects
- dict
- dataclasses
"""

        if risk_decision is None:
            return {}

        if hasattr(risk_decision, "model_dump"):
            return risk_decision.model_dump()

        if hasattr(risk_decision, "to_dict"):
            return risk_decision.to_dict()

        if isinstance(risk_decision, dict):
            return risk_decision

        try:
            return vars(risk_decision)
        except TypeError:
            return {
                "value": str(risk_decision)
            }


    # ---------------------------------------------------------
    # Kill Switch Reasons
    # ---------------------------------------------------------

LOSS_LIMIT_REASONS = {
        "MAX_DAILY_LOSS_EXCEEDED",
        "DAILY_LOSS_LIMIT_REACHED",
        "MAX_LOSS_LIMIT_BREACHED",
    }


    # ---------------------------------------------------------
    # Audit Risk Decision
    # ---------------------------------------------------------

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
        """
        Audit risk engine decision.

        Records:
        - allowed/rejected decision
        - reason
        - kill switch activation
        """

        payload = _serialize_risk_decision(
            risk_decision
        )

        allowed = bool(
            payload.get("allowed")
        )

        reason = str(
            payload.get("reason") or ""
        ).upper()


        # -----------------------------------------------------
        # Risk Decision Audit
        # -----------------------------------------------------

        write_audit_log(
            db=db,
            action="risk_decision",
            actor=actor,
            target_type="symbol",
            target_id=symbol,
            request=request,
            metadata={
                "strategy": strategy,
                "side": side,
                "status": (
                    "allowed"
                    if allowed
                    else "rejected"
                ),
                "risk_allowed": allowed,
                "risk_reason": reason,
                "risk_decision": payload,
            },
        )


        # -----------------------------------------------------
        # Kill Switch Audit
        # -----------------------------------------------------

        if (
            not allowed
            and reason in LOSS_LIMIT_REASONS
        ):

            write_audit_log(
                db=db,
                action="kill_switch_activated",
                actor=actor,
                target_type="symbol",
                target_id=symbol,
                request=request,
                metadata={
                    "strategy": strategy,
                    "side": side,
                    "status": "activated",
                    "reason": reason,
                    "risk_decision": payload,
                },
            )


    # ---------------------------------------------------------
    # Live Guardrail Rejection Handler
    # ---------------------------------------------------------

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
        Reject live order because a live trading
        guardrail failed.
        """


        # ---------------------------------------------
        # Audit Risk Decision First
        # ---------------------------------------------

        _audit_risk_decision(
            db=db,
            request=request,
            actor=actor,
            symbol=signal.symbol,
            strategy=signal.strategy_name,
            side=signal.side,
            risk_decision=risk_decision,
        )


        # ---------------------------------------------
        # Build Response
        # ---------------------------------------------

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


        # ---------------------------------------------
        # Execution Block Audit
        # ---------------------------------------------

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
