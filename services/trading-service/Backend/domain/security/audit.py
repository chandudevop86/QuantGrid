from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from Backend.domain.security.models import AuditLog, User


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
    sanitized_metadata = metadata or {}
    for forbidden in ("password", "new_password", "old_password", "token", "access_token"):
        sanitized_metadata.pop(forbidden, None)

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
