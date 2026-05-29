from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from Backend.core.config import get_settings
from Backend.infrastructure.broker.dhan_status import check_dhan_profile
from Backend.presentation.api.roles import require_roles


router = APIRouter(tags=["broker"])


class DhanLoginRequest(BaseModel):
    client_id: str = Field(min_length=1)
    access_token: str = Field(min_length=1)
    persist: bool = True


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
    status["real_money_orders_enabled"] = False
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
    status["real_money_orders_enabled"] = False
    status["live_trading_enabled"] = get_settings().live_trading_enabled
    return status
