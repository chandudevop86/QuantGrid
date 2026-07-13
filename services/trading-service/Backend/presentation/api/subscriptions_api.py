from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from Backend.application.subscriptions import ENTITLEMENTS, PLANS, list_plans, normalize_plan_code, require_entitlement, subscription_for_user
from Backend.core.database import get_db
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User, UserEntitlementOverride, UserSubscription
from Backend.presentation.api.auth import current_user, require_admin

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class SubscriptionAssignment(BaseModel):
    plan_code: str
    status: Literal["active", "trialing", "past_due", "cancelled", "expired", "suspended"] = "active"
    period_days: int | None = Field(default=30, ge=1, le=3660)
    cancel_at_period_end: bool = False


class EntitlementOverrideRequest(BaseModel):
    entitlement_key: str
    enabled: bool = True
    limit_value: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=3, max_length=255)
    expires_at: datetime | None = None


@router.get("/plans")
def plans() -> dict:
    return {"plans": list_plans(), "currency": "INR", "billing_provider_configured": False}


@router.get("/me")
def my_subscription(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return subscription_for_user(db, user)


@router.get("/admin/users")
def admin_subscriptions(_admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    users = db.query(User).order_by(User.username).all()
    return {"subscriptions": [subscription_for_user(db, user) for user in users]}


@router.put("/admin/users/{user_id}")
def assign_subscription(
    user_id: int,
    payload: SubscriptionAssignment,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    normalized_plan = normalize_plan_code(payload.plan_code)
    if payload.plan_code.lower() not in PLANS and payload.plan_code.lower() not in {"starter", "institutional"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown subscription plan.")
    subscription = db.query(UserSubscription).filter(UserSubscription.user_id == user.id).one_or_none()
    now = datetime.now(timezone.utc)
    if subscription is None:
        subscription = UserSubscription(user_id=user.id)
        db.add(subscription)
    subscription.plan_code = normalized_plan
    subscription.status = payload.status
    subscription.started_at = now
    subscription.current_period_end = now + timedelta(days=payload.period_days) if payload.period_days else None
    subscription.cancel_at_period_end = int(payload.cancel_at_period_end)
    subscription.provider = "manual"
    db.commit()
    write_audit_log(
        db,
        action="subscription_assigned",
        actor=admin,
        target_type="user_subscription",
        target_id=user.id,
        request=request,
        metadata={"plan_code": normalized_plan, "status": payload.status, "period_days": payload.period_days},
    )
    return subscription_for_user(db, user)


@router.get("/admin/entitlements")
def entitlement_catalog(_access=Depends(require_entitlement("admin.subscriptions"))) -> dict:
    return {"entitlements": [{"key": key, **value} for key, value in ENTITLEMENTS.items()]}


@router.post("/admin/users/{user_id}/overrides")
def add_entitlement_override(
    user_id: int,
    payload: EntitlementOverrideRequest,
    request: Request,
    admin: User = Depends(require_admin),
    _access=Depends(require_entitlement("admin.subscriptions")),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if payload.entitlement_key not in ENTITLEMENTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown entitlement key.")
    override = UserEntitlementOverride(
        user_id=user_id, entitlement_key=payload.entitlement_key, enabled=int(payload.enabled),
        limit_value=payload.limit_value, reason=payload.reason, expires_at=payload.expires_at, created_by=admin.id,
    )
    db.add(override)
    db.commit()
    db.refresh(override)
    write_audit_log(db, action="user_entitlement_override_added", actor=admin, target_type="user_entitlement_override", target_id=override.id, request=request, metadata={"user_id": user_id, "entitlement_key": payload.entitlement_key, "enabled": payload.enabled})
    return subscription_for_user(db, user)


@router.delete("/admin/overrides/{override_id}")
def remove_entitlement_override(
    override_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    _access=Depends(require_entitlement("admin.subscriptions")),
    db: Session = Depends(get_db),
) -> dict:
    override = db.get(UserEntitlementOverride, override_id)
    if override is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entitlement override not found.")
    user_id = override.user_id
    db.delete(override)
    db.commit()
    write_audit_log(db, action="user_entitlement_override_removed", actor=admin, target_type="user_entitlement_override", target_id=override_id, request=request, metadata={"user_id": user_id})
    return {"removed": True}
