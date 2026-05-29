from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from fastapi import Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from Backend.domain.security.models import AuditLog, User


TRACKED_ACTIONS = {
    "login_success",
    "login_failure",
    "signal_generated",
    "paper_order_submitted",
    "execution_blocked",
    "user_created",
    "password_changed",
    "password_reset",
}

ACTION_LABELS = {
    "login_success": "Login",
    "login_failure": "Login",
    "signal_generated": "Signal generated",
    "paper_order_submitted": "Order submitted",
    "execution_blocked": "Order rejected",
    "user_created": "User created",
    "password_changed": "Password changed",
    "password_reset": "Password changed",
}


def request_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def request_user_agent(request: Request | None) -> str | None:
    return request.headers.get("user-agent") if request is not None else None


def write_audit_log(
    db: Session,
    *,
    action: str,
    actor: User | None = None,
    actor_username: str | None = None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    request: Request | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    sanitized_metadata = _sanitize_metadata(deepcopy(metadata or {}))

    db.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            actor_username=actor.username if actor else actor_username,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            ip_address=request_ip(request),
            user_agent=request_user_agent(request),
            metadata_json=json.dumps(sanitized_metadata),
        )
    )
    db.commit()


def list_audit_events(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action.in_(TRACKED_ACTIONS))
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .limit(max(1, min(int(limit), 100)))
        .all()
    )
    return [_present_audit_event(row) for row in rows]


def _present_audit_event(row: AuditLog) -> dict[str, Any]:
    metadata = _safe_metadata(row.metadata_json)
    return {
        "id": row.id,
        "timestamp": row.created_at.isoformat() if row.created_at else None,
        "user": row.actor_username or "system",
        "action": ACTION_LABELS.get(row.action, row.action.replace("_", " ").title()),
        "status": _event_status(row.action, metadata),
        "target_type": row.target_type,
        "target_id": row.target_id,
    }


def _safe_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return _sanitize_metadata(parsed if isinstance(parsed, dict) else {})


def _event_status(action: str, metadata: dict[str, Any]) -> str:
    explicit = metadata.get("status")
    if explicit:
        return str(explicit)
    if action.endswith("_failure"):
        return "failed"
    if action in {"execution_blocked"}:
        return "rejected"
    if action in {"signal_generated"}:
        validated = metadata.get("validated_signals")
        return "generated" if isinstance(validated, int) and validated > 0 else "no_signal"
    return "success"


def _sanitize_metadata(value: Any) -> Any:
    forbidden = {"password", "new_password", "old_password", "token", "access_token", "authorization"}
    if isinstance(value, dict):
        return {
            key: ("[redacted]" if str(key).lower() in forbidden else _sanitize_metadata(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_metadata(item) for item in value]
    return value
