from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from Backend.core.database import get_db
from Backend.domain.security.models import User, UserEntitlementOverride, UserSubscription
from Backend.presentation.api.auth import current_user


ENTITLEMENTS: dict[str, dict[str, str]] = {
    "dashboard.basic": {"name": "Dashboard summary", "category": "dashboard"},
    "dashboard.advanced": {"name": "Advanced dashboard", "category": "dashboard"},
    "market.live": {"name": "Live market data", "category": "market"},
    "market.delayed": {"name": "Delayed market data", "category": "market"},
    "decision.basic": {"name": "Market decision", "category": "decision"},
    "decision.advanced_reasons": {"name": "Advanced decision reasons", "category": "decision"},
    "levels.basic": {"name": "Basic levels", "category": "levels"},
    "levels.full": {"name": "Full key levels", "category": "levels"},
    "signals.recent_5": {"name": "Latest five signals", "category": "signals"},
    "signals.recent_25": {"name": "Latest 25 signals", "category": "signals"},
    "signals.unlimited": {"name": "Full signal history", "category": "signals"},
    "chart.basic": {"name": "Basic market chart", "category": "chart"},
    "chart.advanced": {"name": "Advanced chart analytics", "category": "chart"},
    "volume.basic": {"name": "Volume and VWAP", "category": "volume"},
    "volume.advanced": {"name": "Advanced volume profile", "category": "volume"},
    "options.basic": {"name": "Option-chain analysis", "category": "options"},
    "options.advanced": {"name": "Advanced options analytics", "category": "options"},
    "institutional.flow": {"name": "Institutional flow", "category": "institutional"},
    "smart_money.analysis": {"name": "Smart money analysis", "category": "institutional"},
    "strategy.single": {"name": "Single strategy", "category": "strategy"},
    "strategy.multiple": {"name": "Multiple strategies", "category": "strategy"},
    "strategy.performance": {"name": "Strategy performance", "category": "strategy"},
    "backtest.basic": {"name": "Backtesting", "category": "backtest"},
    "backtest.advanced": {"name": "Advanced backtesting", "category": "backtest"},
    "risk.basic": {"name": "Basic risk", "category": "risk"},
    "risk.advanced": {"name": "Advanced risk metrics", "category": "risk"},
    "alerts.basic": {"name": "Basic alerts", "category": "alerts"},
    "alerts.advanced": {"name": "Advanced alerts", "category": "alerts"},
    "paper_trade.manual": {"name": "Manual paper trading", "category": "execution"},
    "paper_trade.automated": {"name": "Automated paper trading", "category": "execution"},
    "live_trade.request": {"name": "Request live trading", "category": "execution"},
    "live_trade.execute": {"name": "Live trading", "category": "execution"},
    "export.csv": {"name": "CSV export", "category": "export"},
    "export.full": {"name": "Full export", "category": "export"},
    "api.access": {"name": "API access", "category": "platform"},
    "admin.users": {"name": "User management", "category": "admin"},
    "admin.subscriptions": {"name": "Subscription management", "category": "admin"},
    "admin.audit": {"name": "Audit logs", "category": "admin"},
    "admin.system": {"name": "System health", "category": "admin"},
    "admin.broker": {"name": "Broker configuration", "category": "admin"},
}

FREE = {
    "dashboard.basic", "market.delayed", "decision.basic", "levels.basic", "signals.recent_5",
    "chart.basic", "strategy.single", "risk.basic", "paper_trade.manual",
}
BASIC = FREE | {
    "market.live", "levels.full", "signals.recent_25", "volume.basic", "strategy.performance", "alerts.basic",
}
PRO = BASIC | {
    "dashboard.advanced", "decision.advanced_reasons", "options.basic", "options.advanced",
    "institutional.flow", "strategy.multiple", "backtest.basic", "backtest.advanced", "risk.advanced",
    "alerts.advanced", "paper_trade.automated", "export.csv", "live_trade.request",
}
PREMIUM = PRO | {
    "chart.advanced", "volume.advanced", "smart_money.analysis", "signals.unlimited", "export.full", "api.access",
}
ADMIN = set(ENTITLEMENTS)

PLANS: dict[str, dict[str, Any]] = {
    "free": {"name": "Free", "description": "Core delayed decision support and manual paper trading.", "price_monthly_inr": 0, "entitlements": FREE, "limits": {"signals_history_limit": 5, "watchlist_limit": 1, "backtest_runs_per_day": 0, "exports_per_month": 0}},
    "basic": {"name": "Basic", "description": "Live market context, full levels, checklist, VWAP, and basic alerts.", "price_monthly_inr": 499, "entitlements": BASIC, "limits": {"signals_history_limit": 25, "watchlist_limit": 3, "backtest_runs_per_day": 0, "exports_per_month": 5}},
    "pro": {"name": "Pro", "description": "Options analytics, backtesting, advanced risk, and automation.", "price_monthly_inr": 1499, "entitlements": PRO, "limits": {"signals_history_limit": 500, "watchlist_limit": 10, "backtest_runs_per_day": 10, "exports_per_month": 50}},
    "premium": {"name": "Premium", "description": "Institutional, smart-money, portfolio, export, and API capabilities.", "price_monthly_inr": 4999, "entitlements": PREMIUM, "limits": {"signals_history_limit": None, "watchlist_limit": 50, "backtest_runs_per_day": 100, "exports_per_month": None}},
    "admin": {"name": "Admin", "description": "Full platform administration and feature configuration.", "price_monthly_inr": 0, "entitlements": ADMIN, "limits": {"signals_history_limit": None, "watchlist_limit": None, "backtest_runs_per_day": None, "exports_per_month": None}, "is_public": False},
}
PLAN_ALIASES = {"starter": "basic", "institutional": "premium"}
ACTIVE_STATUSES = {"active", "trialing"}


def normalize_plan_code(code: str | None) -> str:
    value = str(code or "free").strip().lower()
    return PLAN_ALIASES.get(value, value) if PLAN_ALIASES.get(value, value) in PLANS else "free"


def list_plans(*, include_private: bool = False) -> list[dict[str, Any]]:
    return [
        {"code": code, "name": plan["name"], "description": plan["description"], "price_monthly_inr": plan["price_monthly_inr"], "entitlements": sorted(plan["entitlements"]), "features": sorted(plan["entitlements"]), "limits": dict(plan["limits"]), "is_public": plan.get("is_public", True)}
        for code, plan in PLANS.items() if include_private or plan.get("is_public", True)
    ]


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def subscription_for_user(db: Session, user: User) -> dict[str, Any]:
    subscription = db.query(UserSubscription).filter(UserSubscription.user_id == user.id).one_or_none()
    return _snapshot(db, user, subscription)


def has_entitlement(snapshot: dict[str, Any], feature: str) -> bool:
    return feature in snapshot.get("entitlements", []) and snapshot.get("effective_status") in ACTIVE_STATUSES


def _snapshot(db: Session, user: User, subscription: UserSubscription | None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    plan_code = "admin" if user.role == "admin" else normalize_plan_code(subscription.plan_code if subscription else "free")
    plan = PLANS[plan_code]
    source_status = subscription.status if subscription else "active"
    period_end = _aware(subscription.current_period_end) if subscription else None
    effective_status = source_status
    if period_end and period_end <= now and source_status in ACTIVE_STATUSES:
        effective_status = "expired"
    if source_status in {"suspended", "expired", "past_due"}:
        effective_status = source_status
    entitlements = set(plan["entitlements"] if effective_status in ACTIVE_STATUSES else FREE)
    limits = dict(plan["limits"] if effective_status in ACTIVE_STATUSES else PLANS["free"]["limits"])
    overrides = db.query(UserEntitlementOverride).filter(UserEntitlementOverride.user_id == user.id).all()
    for override in overrides:
        expires_at = _aware(override.expires_at)
        if expires_at and expires_at <= now:
            continue
        if override.enabled:
            entitlements.add(override.entitlement_key)
        else:
            entitlements.discard(override.entitlement_key)
        if override.limit_value is not None:
            limits[override.entitlement_key] = override.limit_value
    return {
        "user_id": user.id, "username": user.username, "plan_code": plan_code, "plan_name": plan["name"],
        "status": source_status, "effective_status": effective_status, "subscription_status": effective_status,
        "entitlements": sorted(entitlements), "features": sorted(entitlements), "limits": limits,
        "price_monthly_inr": plan["price_monthly_inr"],
        "started_at": (subscription.started_at if subscription else user.created_at).isoformat(),
        "current_period_end": period_end.isoformat() if period_end else None,
        "expires_at": period_end.isoformat() if period_end else None,
        "cancel_at_period_end": bool(subscription.cancel_at_period_end) if subscription else False,
        "provider": subscription.provider if subscription else "system_default",
    }


@dataclass(frozen=True)
class SubscriptionAccess:
    user: User
    snapshot: dict[str, Any]

    def can(self, feature: str) -> bool:
        return has_entitlement(self.snapshot, feature)

    def limit(self, key: str) -> int | None:
        value = self.snapshot.get("limits", {}).get(key)
        return int(value) if value is not None else None


def _denied(access: SubscriptionAccess, features: Iterable[str]) -> HTTPException:
    requested = list(features)
    required_plans = [code.upper() for code, plan in PLANS.items() if code != "admin" and any(item in plan["entitlements"] for item in requested)]
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
        "error": "subscription_required", "feature": requested[0] if len(requested) == 1 else requested,
        "current_plan": access.snapshot["plan_code"].upper(), "required_plans": required_plans,
        "message": "Your active subscription does not include this feature.",
    })


def subscription_access(user: User = Depends(current_user), db: Session = Depends(get_db)) -> SubscriptionAccess:
    return SubscriptionAccess(user=user, snapshot=subscription_for_user(db, user))


def require_entitlement(feature: str):
    def dependency(access: SubscriptionAccess = Depends(subscription_access)) -> SubscriptionAccess:
        if not access.can(feature):
            raise _denied(access, [feature])
        return access
    return dependency


def require_any_entitlement(features: Iterable[str]):
    required = tuple(features)
    def dependency(access: SubscriptionAccess = Depends(subscription_access)) -> SubscriptionAccess:
        if not any(access.can(feature) for feature in required):
            raise _denied(access, required)
        return access
    return dependency


def require_all_entitlements(features: Iterable[str]):
    required = tuple(features)
    def dependency(access: SubscriptionAccess = Depends(subscription_access)) -> SubscriptionAccess:
        if not all(access.can(feature) for feature in required):
            raise _denied(access, required)
        return access
    return dependency
