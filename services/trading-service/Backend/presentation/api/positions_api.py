from __future__ import annotations

from fastapi import APIRouter, Depends

from Backend.application.position_store import list_closed_positions, list_open_positions, position_summary
from Backend.presentation.api.roles import require_roles


router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("/open")
def open_positions(_role: str = Depends(require_roles("admin", "developer", "trader", "viewer", "ops"))):
    return {"positions": list_open_positions()}


@router.get("/closed")
def closed_positions(_role: str = Depends(require_roles("admin", "developer", "trader", "viewer", "ops"))):
    return {"positions": list_closed_positions()}


@router.get("/summary")
def summary(_role: str = Depends(require_roles("admin", "developer", "trader", "viewer", "ops"))):
    return position_summary()
