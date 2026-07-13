from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from Backend.core.config import get_settings, reload_settings
from Backend.core.database import get_db
from Backend.application.broker_reconciliation import reconcile_broker_state, reconciliation_status
from Backend.application.broker_circuit_breaker import broker_circuit_status, reset_broker_circuit
from Backend.application.job_queue import enqueue_job
from Backend.domain.security.audit import write_audit_log
from Backend.domain.security.models import User
from Backend.infrastructure.broker.broker_client import broker_client_for_mode
from Backend.infrastructure.broker.dhan_status import cached_dhan_profile, check_dhan_profile
from Backend.presentation.api.roles import current_user, require_roles
from Backend.presentation.api.upstream_errors import upstream_service_error
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


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _live_readiness(settings) -> dict[str, object]:
    circuit = broker_circuit_status()
    app_managed_stops = _truthy(os.getenv("QUANTGRID_ALLOW_APP_MANAGED_STOPS"))
    exit_monitor_enabled = _truthy(os.getenv("QUANTGRID_EXIT_MONITOR_ENABLED"))
    exit_monitor_mode = str(os.getenv("QUANTGRID_EXIT_MONITOR_MODE") or "paper").strip().lower()
    exit_monitor_interval = _float_env("QUANTGRID_EXIT_MONITOR_INTERVAL_SECONDS", 0.0)
    exit_monitor_live_ready = bool(exit_monitor_enabled and exit_monitor_mode == "live" and 1 <= exit_monitor_interval <= 10)
    stop_protection_ready = bool((not app_managed_stops) or exit_monitor_live_ready)
    return {
        "app_managed_stops_allowed": app_managed_stops,
        "exit_monitor_enabled": exit_monitor_enabled,
        "exit_monitor_mode": exit_monitor_mode,
        "exit_monitor_interval_seconds": exit_monitor_interval,
        "exit_monitor_live_ready": exit_monitor_live_ready,
        "stop_protection_ready": stop_protection_ready,
        "broker_circuit_breaker_active": bool(circuit.get("active")),
        "live_ready": bool(
            settings.live_trading_enabled
            and settings.broker_live_enabled
            and settings.broker_configured
            and settings.risk_configured
            and settings.audit_logging_enabled
            and stop_protection_ready
            and not circuit.get("active")
        ),
    }


def _dhan_option_chain_readiness(symbol: str = "NIFTY") -> dict[str, object]:
    profile = check_dhan_profile()
    normalized = symbol.upper()
    base = {
        "provider": "dhan",
        "symbol": normalized,
        "profile_connected": bool(profile.get("connected")),
        "profile_error": profile.get("error"),
        "option_chain_access": False,
        "data_api_connected": False,
        "expiry_available": False,
        "expiry": None,
        "message": "",
        "suggested_actions": [],
    }
    if not profile.get("connected"):
        return base | {
            "message": "Dhan profile check is not connected; fix client ID/access token first.",
            "suggested_actions": ["Open Dhan Login and save a valid access token.", "Confirm QUANTGRID_BROKER_CLIENT_ID matches the token account."],
        }

    try:
        from Backend.presentation.api import market_api

        security_id, exchange_segment = market_api._dhan_underlying(normalized)
        expiry_payload = market_api._dhan_option_provider_payload(
            "optionchain/expirylist",
            {"UnderlyingScrip": security_id, "UnderlyingSeg": exchange_segment},
        )
        expiries = market_api._dhan_expiry_values(expiry_payload)
        expiry = next((str(item) for item in expiries if item), None)
        if not expiry:
            return base | {
                "profile_connected": True,
                "data_api_connected": True,
                "message": "Dhan Data API responded, but no option-chain expiry was returned.",
                "suggested_actions": ["Verify NIFTY underlying security ID and exchange segment configuration.", "Retry during market hours."],
            }
        return base | {
            "profile_connected": True,
            "option_chain_access": True,
            "data_api_connected": True,
            "expiry_available": True,
            "expiry": expiry,
            "message": "Dhan profile and option-chain Data API checks passed.",
            "suggested_actions": [],
        }
    except Exception as exc:
        return base | {
            "profile_connected": True,
            "message": str(exc),
            "suggested_actions": [
                "Verify Dhan Data APIs / Option Chain are enabled for this account.",
                "Verify this server's outbound static IP is whitelisted with Dhan.",
                "Confirm QUANTGRID_BROKER_CLIENT_ID matches the profile dhanClientId.",
                "Refresh the Dhan access token after entitlement or IP whitelist changes.",
            ],
        }


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
        status = cached_dhan_profile()
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
    status["risk_configured"] = settings.risk_configured
    status["audit_logging_enabled"] = settings.audit_logging_enabled
    status["circuit_breaker"] = broker_circuit_status()
    status["live_readiness"] = _live_readiness(settings)
    status["real_money_orders_enabled"] = bool(
        settings.live_trading_enabled
        and settings.broker_live_enabled
        and settings.broker_configured
        and status.get("connected")
        and not status["circuit_breaker"].get("active")
    )
    return status


@router.get("/dhan/option-chain/status")
def dhan_option_chain_status(
    symbol: str = "NIFTY",
    _role: str = Depends(require_roles("admin", "developer", "trader", "ops")),
):
    return _dhan_option_chain_readiness(symbol)


@router.post("/dhan/login")
def dhan_login(payload: DhanLoginRequest, _role: str = Depends(require_roles("admin", "trader", "ops"))):
    if payload.persist and _role not in {"admin", "ops"}:
        # Authorize before mutating process-wide credentials. A rejected request
        # must not alter the broker used by other sessions in this process.
        raise HTTPException(status_code=403, detail="Only admins or ops can persist global Dhan credentials.")
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

    settings = reload_settings()
    status = check_dhan_profile()
    status["saved"] = bool(payload.persist)
    status["live_trading_enabled"] = settings.live_trading_enabled
    status["broker_live_enabled"] = settings.broker_live_enabled
    status["risk_configured"] = settings.risk_configured
    status["audit_logging_enabled"] = settings.audit_logging_enabled
    status["circuit_breaker"] = broker_circuit_status()
    status["live_readiness"] = _live_readiness(settings)
    status["real_money_orders_enabled"] = bool(
        settings.live_trading_enabled
        and settings.broker_live_enabled
        and settings.broker_configured
        and status.get("connected")
        and not status["circuit_breaker"].get("active")
    )
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
        raise upstream_service_error("broker", "cancel_order", exc) from exc
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
        raise upstream_service_error("broker", "get_order_status", exc) from exc
    return result.to_dict()


@router.get("/positions")
async def get_positions(
    _role: str = Depends(require_roles("admin", "developer", "trader", "ops")),
    execution_mode: str = Depends(_execution_mode),
):
    try:
        return {"positions": await broker_client_for_mode(execution_mode).get_positions()}
    except Exception as exc:
        raise upstream_service_error("broker", "get_positions", exc) from exc


@router.get("/holdings")
async def get_holdings(
    _role: str = Depends(require_roles("admin", "developer", "trader", "ops")),
    execution_mode: str = Depends(_execution_mode),
):
    try:
        return {"holdings": await broker_client_for_mode(execution_mode).get_holdings()}
    except Exception as exc:
        raise upstream_service_error("broker", "get_holdings", exc) from exc


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
        raise upstream_service_error("broker", "reconcile", exc) from exc


@router.post("/reconcile/jobs")
def enqueue_reconciliation_job(
    request: Request,
    actor: User = Depends(current_user),
    _role: str = Depends(require_roles("admin", "developer", "trader", "ops")),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    job = enqueue_job(
        "order-reconciliation",
        {"execution_mode": execution_mode},
        metadata={"execution_mode": execution_mode},
    )
    write_audit_log(
        db,
        action="trading_job_created",
        actor=actor,
        target_type="job",
        target_id=job["job_id"],
        request=request,
        metadata={"job_type": "order-reconciliation", "execution_mode": execution_mode, "status": "queued"},
    )
    return job


@router.get("/reconciliation/status")
def get_reconciliation_status(_role: str = Depends(require_roles("admin", "developer", "trader", "ops"))):
    return reconciliation_status()


@router.get("/circuit-breaker/status")
def get_broker_circuit_breaker_status(_role: str = Depends(require_roles("admin", "developer", "trader", "viewer", "ops"))):
    return broker_circuit_status()


@router.post("/circuit-breaker/reset")
def reset_broker_circuit_breaker(
    request: Request,
    actor: User = Depends(current_user),
    _role: str = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    status_payload = reset_broker_circuit(actor=actor.username)
    write_audit_log(
        db,
        action="broker_circuit_breaker_reset",
        actor=actor,
        target_type="broker",
        target_id="live",
        request=request,
        metadata={"status": "reset", "reason": "Manual admin reset", "circuit_breaker": status_payload},
    )
    return status_payload
