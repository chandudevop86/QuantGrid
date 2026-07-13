from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from Backend.domain.security.models import User, UserSubscription


PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "name": "Free",
        "price_monthly_inr": 0,
        "description": "Core market decision and paper-trading workspace.",
        "features": ["dashboard", "options_market", "paper_portfolio"],
    },
    "starter": {
        "name": "Starter",
        "price_monthly_inr": 499,
        "description": "Signal qualification and strategy backtesting for active learners.",
        "features": ["dashboard", "options_market", "paper_portfolio", "qualified_signals", "backtesting"],
    },
    "pro": {
        "name": "Pro",
        "price_monthly_inr": 1499,
        "description": "Advanced analysis, strategy tools, and decision explainability.",
        "features": [
            "dashboard", "options_market", "paper_portfolio", "qualified_signals", "backtesting",
            "live_analysis", "market_copilot", "strategies", "trade_journal",
        ],
    },
    "institutional": {
        "name": "Institutional",
        "price_monthly_inr": 4999,
        "description": "Full research, institutional context, operations, and team capabilities.",
        "features": ["*"],
    },
}

ACTIVE_STATUSES = {"active", "trialing"}


def list_plans() -> list[dict[str, Any]]:
    return [{"code": code, **plan} for code, plan in PLANS.items()]


def subscription_for_user(db: Session, user: User) -> dict[str, Any]:
    subscription = db.query(UserSubscription).filter(UserSubscription.user_id == user.id).one_or_none()
    if subscription is None:
        return _snapshot(user, None)
    return _snapshot(user, subscription)


def has_entitlement(snapshot: dict[str, Any], feature: str) -> bool:
    return bool(snapshot.get("effective_status") in ACTIVE_STATUSES and ("*" in snapshot.get("features", []) or feature in snapshot.get("features", [])))


def _snapshot(user: User, subscription: UserSubscription | None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    plan_code = subscription.plan_code if subscription and subscription.plan_code in PLANS else "free"
    plan = PLANS[plan_code]
    status = subscription.status if subscription else "active"
    period_end = subscription.current_period_end if subscription else None
    if period_end is not None:
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
        if period_end <= now and status in ACTIVE_STATUSES:
            status = "expired"
    return {
        "user_id": user.id,
        "username": user.username,
        "plan_code": plan_code,
        "plan_name": plan["name"],
        "status": subscription.status if subscription else "active",
        "effective_status": status,
        "features": list(plan["features"]),
        "price_monthly_inr": plan["price_monthly_inr"],
        "started_at": subscription.started_at.isoformat() if subscription else user.created_at.isoformat(),
        "current_period_end": period_end.isoformat() if period_end else None,
        "cancel_at_period_end": bool(subscription.cancel_at_period_end) if subscription else False,
        "provider": subscription.provider if subscription else "system_default",
    }
