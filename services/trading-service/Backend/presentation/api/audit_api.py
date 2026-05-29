from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from Backend.core.database import get_db
from Backend.domain.security.audit import list_audit_events
from Backend.presentation.api.roles import require_roles


router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
def audit_logs(
    limit: int = 50,
    _role: str = Depends(require_roles("admin", "developer", "ops")),
    db: Session = Depends(get_db),
):
    return {"events": list_audit_events(db, limit)}
