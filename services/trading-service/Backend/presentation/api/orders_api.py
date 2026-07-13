from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from Backend.application.order_store import (
    broker_status_to_order_status,
    get_order,
    list_orders,
    transition_order,
)
from Backend.core.database import get_db
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User
from Backend.infrastructure.broker.broker_client import broker_client_for_mode
from Backend.presentation.api.roles import current_user, require_roles
from Backend.presentation.api.upstream_errors import upstream_service_error


router = APIRouter(prefix="/orders", tags=["orders"])


def _execution_mode(x_quantgrid_mode: str = Header(default="paper", alias="X-QuantGrid-Mode")) -> str:
    mode = x_quantgrid_mode.strip().lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid execution mode.")
    return mode


@router.get("")
def get_orders(
    limit: int = 100,
    _role: str = Depends(require_roles("admin", "developer", "trader", "viewer", "ops")),
):
    return {"orders": list_orders(limit)}


@router.get("/{local_order_id}")
def get_order_by_id(
    local_order_id: str,
    _role: str = Depends(require_roles("admin", "developer", "trader", "viewer", "ops")),
):
    order = get_order(local_order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return order


@router.post("/{local_order_id}/cancel")
async def cancel_order(
    local_order_id: str,
    request: Request,
    actor: User = Depends(current_user),
    _role: str = Depends(require_roles("admin", "trader", "ops")),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    order = get_order(local_order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    broker_order_id = order.get("broker_order_id")
    if not broker_order_id:
        updated, previous = transition_order(local_order_id, "cancelled", status_reason="Cancelled before broker submission.")
        _audit_transition(db, request, actor, updated, previous)
        return updated

    try:
        broker_result = await broker_client_for_mode(execution_mode).cancel_order(str(broker_order_id))
    except Exception as exc:
        updated, previous = transition_order(local_order_id, "failed", status_reason="broker_cancel_unavailable")
        _audit_transition(db, request, actor, updated, previous)
        raise upstream_service_error("broker", "cancel_order", exc) from exc

    next_status = broker_status_to_order_status(broker_result.status, confirmed=broker_result.confirmed)
    if next_status not in {"cancelled", "failed", "rejected"}:
        next_status = "cancelled" if broker_result.confirmed else "pending"
    updated, previous = transition_order(
        local_order_id,
        next_status,
        status_reason=broker_result.message or f"Broker cancel status: {broker_result.status}",
        broker_order_id=broker_result.broker_order_id,
        broker_status=broker_result.status,
        entry_price=broker_result.price,
    )
    _audit_transition(db, request, actor, updated, previous, broker_result.to_dict())
    return updated


def _audit_transition(
    db: Session,
    request: Request,
    actor: User,
    order: dict,
    previous_status: str,
    broker_response: dict | None = None,
) -> None:
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
