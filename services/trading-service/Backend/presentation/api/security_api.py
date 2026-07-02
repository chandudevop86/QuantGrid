from __future__ import annotations

from fastapi import APIRouter, Depends

from Backend.presentation.api.roles import require_roles
from app.security.security_ops_loop import latest_security_dashboard, list_security_scan_history

router = APIRouter(prefix="/security", tags=["security"])

SECURITY_ROLES = ("admin", "developer", "ops")


@router.get("/dashboard")
def security_dashboard(_role: str = Depends(require_roles(*SECURITY_ROLES))):
    return latest_security_dashboard()


@router.get("/findings")
def security_findings(_role: str = Depends(require_roles(*SECURITY_ROLES))):
    payload = latest_security_dashboard()
    return {
        "critical_findings": payload["critical_findings"],
        "warnings": payload["warnings"],
        "recommended_actions": payload["recommended_actions"],
        "trend": list_security_scan_history(limit=20),
    }


@router.get("/network")
def security_network(_role: str = Depends(require_roles(*SECURITY_ROLES))):
    return latest_security_dashboard(category="network")


@router.get("/kubernetes")
def security_kubernetes(_role: str = Depends(require_roles(*SECURITY_ROLES))):
    return latest_security_dashboard(category="kubernetes")


@router.get("/containers")
def security_containers(_role: str = Depends(require_roles(*SECURITY_ROLES))):
    return latest_security_dashboard(category="containers")


@router.get("/iam")
def security_iam(_role: str = Depends(require_roles(*SECURITY_ROLES))):
    return latest_security_dashboard(category="iam")


@router.get("/database")
def security_database(_role: str = Depends(require_roles(*SECURITY_ROLES))):
    return latest_security_dashboard(category="database")


@router.get("/devsecops")
def security_devsecops(_role: str = Depends(require_roles(*SECURITY_ROLES))):
    return latest_security_dashboard(category="devsecops")
