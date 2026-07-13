from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from Backend.application.subscriptions import PLANS, list_plans, subscription_for_user
from Backend.core.database import get_db
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User, UserSubscription
from Backend.presentation.api.auth import current_user, require_admin

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class SubscriptionAssignment(BaseModel):
    plan_code: Literal["free", "starter", "pro", "institutional"]
    status: Literal["active", "trialing", "paused", "cancelled", "expired"] = "active"
    period_days: int | None = Field(default=30, ge=1, le=3660)
    cancel_at_period_end: bool = False


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
    if payload.plan_code not in PLANS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown subscription plan.")
    subscription = db.query(UserSubscription).filter(UserSubscription.user_id == user.id).one_or_none()
    now = datetime.now(timezone.utc)
    if subscription is None:
        subscription = UserSubscription(user_id=user.id)
        db.add(subscription)
    subscription.plan_code = payload.plan_code
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
        metadata={"plan_code": payload.plan_code, "status": payload.status, "period_days": payload.period_days},
    )
    return subscription_for_user(db, user)
