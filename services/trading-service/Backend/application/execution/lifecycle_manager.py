from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from Backend.domain.models.signal import StrategySignal
from Backend.domain.security.models import User

from Backend.application.execution.audit_manager import (
    _audit_order_transition,
)
from Backend.application.order_store import (
    create_order,
    get_active_order_by_key,
    transition_order,
)


def _build_order_key(
    signal: StrategySignal,
) -> str:
    """
    Build the canonical duplicate-detection key.

    The same symbol + side + strategy combination cannot have
    multiple active orders simultaneously.
    """

    return (
        f"{signal.symbol.upper()}:"
        f"{signal.side.upper()}:"
        f"{signal.strategy_name.upper()}"
    )


def _create_lifecycle_order(
    order: Any,
    *,
    signal: StrategySignal,
    execution_mode: str,
    db: Session | None,
    request: Request | None,
    actor: User | None,
) -> dict[str, Any]:
    """
    Create a tracked lifecycle order after duplicate detection.

    Initial state:

        requested

    Expected next states are controlled by the execution pipeline.
    """

    order_key = _build_order_key(signal)

    # ---------------------------------------------------------
    # Duplicate active-order protection
    # ---------------------------------------------------------

    duplicate = get_active_order_by_key(order_key)

    if duplicate is not None:
        duplicate_copy = dict(duplicate)

        duplicate_copy["status_reason"] = (
            "Duplicate active order suppressed "
            "before broker submission."
        )

        _audit_order_transition(
            db=db,
            request=request,
            actor=actor,
            order=duplicate_copy,
            previous_status=duplicate.get(
                "status",
                "active",
            ),
            broker_response={
                "duplicate_order_key": order_key,
            },
        )

        raise ValueError(
            "DUPLICATE_ACTIVE_ORDER: "
            f"{duplicate['local_order_id']}"
        )

    # ---------------------------------------------------------
    # Create local order
    # ---------------------------------------------------------

    local_order = create_order(
        {
            "order_key": order_key,
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
            "status_reason": (
                "Order request accepted for risk review."
            ),
        }
    )

    # ---------------------------------------------------------
    # Audit creation
    # ---------------------------------------------------------

    _audit_order_transition(
        db=db,
        request=request,
        actor=actor,
        order=local_order,
        previous_status="new",
    )

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
    broker_status: str | None = None,
    entry_price: float | None = None,
    broker_response: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Transition a persisted order to its next lifecycle state.

    Every transition is persisted through order_store.py and then
    audited.
    """

    if local_order is None:
        return None

    local_order_id = local_order.get(
        "local_order_id"
    )

    if not local_order_id:
        raise ValueError(
            "ORDER_TRANSITION_FAILED: "
            "local_order_id is missing"
        )

    updated_order, previous_status = transition_order(
        local_order_id=local_order_id,
        status=status_value,
        status_reason=reason,
        broker_order_id=broker_order_id,
        broker_status=broker_status,
        entry_price=entry_price,
    )

    _audit_order_transition(
        db=db,
        request=request,
        actor=actor,
        order=updated_order,
        previous_status=previous_status,
        broker_response=broker_response,
    )

    return updated_order