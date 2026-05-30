from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from Backend.core.config import get_settings
from Backend.core.database import get_db
from Backend.application.broker_reconciliation import reconcile_broker_state, reconciliation_status
from Backend.domain.security.models import User
from Backend.infrastructure.broker.broker_client import broker_client_for_mode
from Backend.infrastructure.broker.dhan_status import check_dhan_profile
from Backend.presentation.api.roles import current_user, require_roles
from sqlalchemy.orm import Session


router = APIRouter(tags=["broker"])


class DhanLoginRequest(BaseModel):
    client_id: str = Field(min_length=1)
    access_token: str = Field(min_length=1)
    persist: bool = True


def _execution_mode(x_quantgrid_mode: str = Header(default="paper", alias="X-QuantGrid-Mode")) -> str:
    mode = x_quantgrid_mode.strip().lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid execution mode.")
    return mode


def _env_file_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".env"


def _write_env_values(path: Path, values: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    order: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                order.append(line)
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            existing[key] = value
            order.append(key)

    existing.update(values)
    for key in values:
        if key not in order:
            order.append(key)

    lines = []
    for item in order:
        if item in existing:
            lines.append(f"{item}={existing[item]}")
        else:
            lines.append(item)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


@router.get("/status")
def broker_status(_role: str = Depends(require_roles("admin", "developer", "trader", "ops"))):
    settings = get_settings()
    provider = settings.broker_provider or "none"

    if provider == "dhan":
        status = check_dhan_profile()
    elif provider == "none":
        status = {
            "provider": "none",
            "configured": False,
            "connected": False,
            "paper_mode": True,
            "message": "No broker is configured. QuantGrid is running in paper mode.",
        }
    else:
        status = {
            "provider": provider,
            "configured": settings.broker_configured,
            "connected": False,
            "paper_mode": True,
            "message": f"Broker status check is not implemented for {provider}.",
        }

    status["live_trading_enabled"] = settings.live_trading_enabled
    status["broker_live_enabled"] = settings.broker_live_enabled
    status["real_money_orders_enabled"] = bool(settings.live_trading_enabled and settings.broker_live_enabled and settings.broker_configured)
    return status


@router.post("/dhan/login")
def dhan_login(payload: DhanLoginRequest, _role: str = Depends(require_roles("admin", "trader"))):
    os.environ["QUANTGRID_BROKER_PROVIDER"] = "dhan"
    os.environ["QUANTGRID_BROKER_CLIENT_ID"] = payload.client_id.strip()
    os.environ["QUANTGRID_BROKER_ACCESS_TOKEN"] = payload.access_token.strip()
    if payload.persist:
        _write_env_values(
            _env_file_path(),
            {
                "QUANTGRID_BROKER_PROVIDER": "dhan",
                "QUANTGRID_BROKER_CLIENT_ID": payload.client_id.strip(),
                "QUANTGRID_BROKER_ACCESS_TOKEN": payload.access_token.strip(),
            },
        )

    status = check_dhan_profile()
    status["saved"] = bool(payload.persist)
    status["live_trading_enabled"] = get_settings().live_trading_enabled
    status["broker_live_enabled"] = get_settings().broker_live_enabled
    status["real_money_orders_enabled"] = bool(get_settings().live_trading_enabled and get_settings().broker_live_enabled and get_settings().broker_configured)
    return status


@router.post("/orders/{broker_order_id}/cancel")
async def cancel_order(
    broker_order_id: str,
    _role: str = Depends(require_roles("admin", "trader")),
    execution_mode: str = Depends(_execution_mode),
):
    try:
        result = await broker_client_for_mode(execution_mode).cancel_order(broker_order_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Broker cancel failed: {exc}") from exc
    return result.to_dict()


@router.get("/orders/{broker_order_id}")
async def get_order_status(
    broker_order_id: str,
    _role: str = Depends(require_roles("admin", "developer", "trader", "ops")),
    execution_mode: str = Depends(_execution_mode),
):
    try:
        result = await broker_client_for_mode(execution_mode).get_order_status(broker_order_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Broker status failed: {exc}") from exc
    return result.to_dict()


@router.get("/positions")
async def get_positions(
    _role: str = Depends(require_roles("admin", "developer", "trader", "ops")),
    execution_mode: str = Depends(_execution_mode),
):
    try:
        return {"positions": await broker_client_for_mode(execution_mode).get_positions()}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Broker positions failed: {exc}") from exc


@router.get("/holdings")
async def get_holdings(
    _role: str = Depends(require_roles("admin", "developer", "trader", "ops")),
    execution_mode: str = Depends(_execution_mode),
):
    try:
        return {"holdings": await broker_client_for_mode(execution_mode).get_holdings()}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Broker holdings failed: {exc}") from exc


@router.post("/reconcile")
async def reconcile_broker(
    request: Request,
    actor: User = Depends(current_user),
    _role: str = Depends(require_roles("admin", "developer", "trader", "ops")),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    try:
        return await reconcile_broker_state(
            db=db,
            broker_client=broker_client_for_mode(execution_mode),
            actor=actor,
            request=request,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Broker reconciliation failed: {exc}") from exc


@router.get("/reconciliation/status")
def get_reconciliation_status(_role: str = Depends(require_roles("admin", "developer", "trader", "ops"))):
    return reconciliation_status()
