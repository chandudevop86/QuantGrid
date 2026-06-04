from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from fastapi import Request
from sqlalchemy import text
from sqlalchemy import desc
from sqlalchemy.orm import Session

from Backend.domain.security.models import AuditLog, User


TRACKED_ACTIONS = {
    "login_success",
    "login_failure",
    "signal_generated",
    "risk_decision",
    "execution_triggered",
    "trading_job_created",
    "order_status_transition",
    "paper_order_submitted",
    "live_order_submitted",
    "execution_blocked",
    "broker_reconciliation_change",
    "broker_failure_recorded",
    "broker_circuit_breaker_activated",
    "broker_circuit_breaker_reset",
    "position_exit",
    "kill_switch_activated",
    "kill_switch_deactivated",
    "kill_switch_activation_denied",
    "user_created",
    "password_changed",
    "password_reset",
}

ACTION_LABELS = {
    "login_success": "Login",
    "login_failure": "Login",
    "signal_generated": "Signal generated",
    "risk_decision": "Risk decision",
    "execution_triggered": "Order requested",
    "trading_job_created": "Job queued",
    "order_status_transition": "Order status transition",
    "paper_order_submitted": "Order placed",
    "live_order_submitted": "Order placed",
    "execution_blocked": "Order failed",
    "broker_reconciliation_change": "Broker reconciliation",
    "broker_failure_recorded": "Broker failure recorded",
    "broker_circuit_breaker_activated": "Broker circuit breaker activated",
    "broker_circuit_breaker_reset": "Broker circuit breaker reset",
    "position_exit": "Position exited",
    "kill_switch_activated": "Kill switch activated",
    "kill_switch_deactivated": "Kill switch deactivated",
    "kill_switch_activation_denied": "Kill switch activation denied",
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


def request_id(request: Request | None) -> str | None:
    if request is None:
        return None
    state_id = getattr(getattr(request, "state", None), "request_id", None)
    return state_id or request.headers.get("x-request-id")


def ensure_audit_schema(db: Session) -> None:
    dialect = db.get_bind().dialect.name
    columns = _audit_columns(db, dialect)
    additions = _audit_column_additions(dialect)
    for column, statement in additions.items():
        if column not in columns:
            db.execute(text(statement))
    db.commit()


def _audit_columns(db: Session, dialect: str) -> set[str]:
    if dialect == "sqlite":
        rows = db.execute(text("PRAGMA table_info(audit_logs)")).fetchall()
        return {str(row[1]) for row in rows}
    rows = db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'audit_logs'
              AND table_schema = current_schema()
            """
        )
    ).fetchall()
    return {str(row[0]) for row in rows}


def _audit_column_additions(dialect: str) -> dict[str, str]:
    if dialect == "postgresql":
        return {
            "actor_role": "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS actor_role VARCHAR(32)",
            "status": "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS status VARCHAR(40)",
            "request_id": "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS request_id VARCHAR(80)",
            "reason": "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS reason VARCHAR(255)",
        }
    return {
        "actor_role": "ALTER TABLE audit_logs ADD COLUMN actor_role VARCHAR(32)",
        "status": "ALTER TABLE audit_logs ADD COLUMN status VARCHAR(40)",
        "request_id": "ALTER TABLE audit_logs ADD COLUMN request_id VARCHAR(80)",
        "reason": "ALTER TABLE audit_logs ADD COLUMN reason VARCHAR(255)",
    }


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
    status_value = _event_status(action, sanitized_metadata)
    reason_value = _event_reason(action, sanitized_metadata)

    db.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            actor_username=actor.username if actor else actor_username,
            actor_role=actor.role if actor else sanitized_metadata.get("role"),
            action=action,
            status=status_value,
            request_id=request_id(request),
            reason=reason_value,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            ip_address=request_ip(request),
            user_agent=request_user_agent(request),
            metadata_json=json.dumps(sanitized_metadata),
        )
    )
    db.commit()


def list_audit_events(db: Session, limit: int = 50) -> list[dict[str, Any]]:
    ensure_audit_schema(db)
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
    status_value = row.status or _event_status(row.action, metadata)
    return {
        "id": row.id,
        "timestamp": row.created_at.isoformat() if row.created_at else None,
        "user": row.actor_username or "system",
        "role": row.actor_role or "-",
        "action": _event_action_label(row.action, status_value),
        "status": status_value,
        "request_id": row.request_id,
        "reason": row.reason or _event_reason(row.action, metadata),
        "metadata": metadata,
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
        return "failed"
    if action in {"kill_switch_activation_denied"}:
        return "denied"
    if action in {"paper_order_submitted", "live_order_submitted"}:
        return "placed"
    if action in {"position_exit"}:
        return "closed"
    if action in {"execution_triggered"}:
        return "requested"
    if action in {"order_status_transition"}:
        return str(metadata.get("to_status") or metadata.get("status") or "updated")
    if action in {"signal_generated"}:
        validated = metadata.get("validated_signals")
        return "generated" if isinstance(validated, int) and validated > 0 else "no_signal"
    if action in {"risk_decision"}:
        return str(metadata.get("status") or "reviewed")
    if action in {"kill_switch_activated"}:
        return "activated"
    if action in {"kill_switch_deactivated"}:
        return "deactivated"
    return "success"


def _event_reason(action: str, metadata: dict[str, Any]) -> str | None:
    reason = metadata.get("reason")
    if reason:
        return str(reason)
    risk_decision = metadata.get("risk_decision")
    if isinstance(risk_decision, dict) and risk_decision.get("reason"):
        return str(risk_decision["reason"])
    if action == "login_failure":
        return "Invalid username or password"
    return None


def _event_action_label(action: str, status_value: str) -> str:
    if action == "risk_decision":
        return "Risk approved" if status_value == "allowed" else "Risk rejected"
    return ACTION_LABELS.get(action, action.replace("_", " ").title())


def _sanitize_metadata(value: Any) -> Any:
    forbidden = {
        "password",
        "new_password",
        "old_password",
        "token",
        "access_token",
        "access-token",
        "authorization",
        "clientsecret",
        "api_secret",
        "apisecret",
    }
    if isinstance(value, dict):
        return {
            key: ("[redacted]" if str(key).lower() in forbidden else _sanitize_metadata(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_metadata(item) for item in value]
    return value
