from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Backend.application.kill_switch import activate_kill_switch, deactivate_kill_switch, kill_switch_status
from Backend.application.portfolio_risk import build_portfolio_risk_dashboard
from Backend.application.subscriptions import require_entitlement
from Backend.core.database import get_db
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User
from Backend.presentation.api.auth import current_user, require_admin
from Backend.presentation.api.roles import require_roles


router = APIRouter(prefix="/risk", tags=["risk"])
KILL_SWITCH_ACTIVATION_ROLES = {"admin", "trader", "ops"}


class KillSwitchActivationRequest(BaseModel):
    reason: str | None = None


@router.get("/kill-switch/status")
def get_kill_switch_status(_role: str = Depends(require_roles("admin", "developer", "trader", "viewer", "ops"))):
    return kill_switch_status()


@router.get("/dashboard")
def portfolio_risk_dashboard(
    symbol: str = "NIFTY",
    entry_price: float | None = None,
    stop_loss: float | None = None,
    atr_multiplier: float = 1.5,
    _access=Depends(require_entitlement("risk.advanced")),
):
    return build_portfolio_risk_dashboard(
        symbol,
        entry_price=entry_price,
        stop_loss=stop_loss,
        atr_multiplier=atr_multiplier,
    )


@router.post("/kill-switch/activate")
def activate(
    payload: KillSwitchActivationRequest,
    request: Request,
    actor: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if actor.role not in KILL_SWITCH_ACTIVATION_ROLES:
        write_audit_log(
            db,
            action="kill_switch_activation_denied",
            actor=actor,
            target_type="risk",
            target_id="kill-switch",
            request=request,
            metadata={"reason": "missing kill-switch activation permission", "role": actor.role},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This role cannot activate the kill switch.")
    kill_switch = activate_kill_switch(reason=payload.reason, actor=actor.username)
    write_audit_log(
        db,
        action="kill_switch_activated",
        actor=actor,
        target_type="risk",
        target_id="kill-switch",
        request=request,
        metadata={"status": "activated", "reason": kill_switch.get("reason"), "kill_switch": kill_switch},
    )
    return kill_switch


@router.post("/kill-switch/deactivate")
def deactivate(
    request: Request,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    status = deactivate_kill_switch(actor=actor.username)
    write_audit_log(
        db,
        action="kill_switch_deactivated",
        actor=actor,
        target_type="risk",
        target_id="kill-switch",
        request=request,
        metadata={"status": "deactivated", "reason": "Manual admin deactivation", "kill_switch": status},
    )
    return status
