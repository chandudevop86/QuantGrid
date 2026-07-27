from __future__ import annotations
import os
from fastapi import Request
from typing import Any

from Backend.domain.models.signal import StrategySignal
from Backend.domain.security.models import User
from fastapi import (
    HTTPException,
    Request,
    status,
)
from Backend.application.broker_circuit_breaker import broker_circuit_status
from Backend.infrastructure.broker.broker_client import (
    broker_client_for_mode
)
from Backend.infrastructure.broker.broker_client import  broker_client_for_mode
from Backend.application.signal_validation import diagnose_signal_run, validate_signals
def _request_is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto.split(",", 1)[0].strip().lower() == "https"


def _allow_insecure_live() -> bool:
    return str(os.getenv("LIVE_ALLOW_INSECURE", "")).strip().lower() in {"1", "true", "yes"}


def _app_managed_stops_allowed() -> bool:
    return str(os.getenv("QUANTGRID_ALLOW_APP_MANAGED_STOPS", "")).strip().lower() in {"1", "true", "yes"}


def _exit_monitor_live_ready() -> bool:
    enabled = str(os.getenv("QUANTGRID_EXIT_MONITOR_ENABLED", "")).strip().lower() in {"1", "true", "yes"}
    mode = str(os.getenv("QUANTGRID_EXIT_MONITOR_MODE", "")).strip().lower()
    try:
        interval = float(os.getenv("QUANTGRID_EXIT_MONITOR_INTERVAL_SECONDS", "0"))
    except ValueError:
        interval = 0.0
    return enabled and mode == "live" and 1 <= interval <= 10
def _require_trading_engine_role(actor: User) -> None:
    if actor.role not in {"admin", "developer", "trader"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This role is not allowed to perform this action.",
        )
def _live_stop_protection_failure(signal: StrategySignal | None) -> str | None:
    """
    Validate that live trading has adequate stop-loss protection.

    Returns:
        None if stop protection is acceptable.
        Error message describing why live execution must be rejected.
    """

    # No signal to validate.
    if signal is None:
        return None

    # ------------------------------------------------------------------
    # Stop Loss
    # ------------------------------------------------------------------
    try:
        stop_loss = float(signal.stop_loss)
    except (TypeError, ValueError):
        stop_loss = 0.0

    if stop_loss <= 0:
        return "Live trading requires a valid stop-loss."

    # ------------------------------------------------------------------
    # Target
    # ------------------------------------------------------------------
    try:
        target = float(signal.target_price)
    except (TypeError, ValueError):
        target = 0.0

    if target <= 0:
        return "Live trading requires a valid target."

    # ------------------------------------------------------------------
    # Broker-native stops are preferred.
    # ------------------------------------------------------------------
    if not _app_managed_stops_allowed():
        return (
            "Live trading requires broker-native stop protection. "
            "App-managed SL/TSL is disabled. "
            "Enable QUANTGRID_ALLOW_APP_MANAGED_STOPS=true only when the "
            "Exit Monitor is continuously running."
        )

    # ------------------------------------------------------------------
    # App-managed stops require a healthy exit monitor.
    # ------------------------------------------------------------------
    if not _exit_monitor_live_ready():
        return (
            "App-managed stop protection is enabled but the Exit Monitor "
            "is not ready. "
            "Required configuration:\n"
            "- QUANTGRID_EXIT_MONITOR_ENABLED=true\n"
            "- QUANTGRID_EXIT_MONITOR_MODE=live\n"
            "- QUANTGRID_EXIT_MONITOR_INTERVAL_SECONDS <= 10"
        )

    # ------------------------------------------------------------------
    # Stop protection verified.
    # ------------------------------------------------------------------
    return None       
def _live_guardrail_failure(
    *,
    request: Request,
    actor: User,
    settings,
    candles_1m: list[dict[str, Any]],
    risk_decision: Any,
    signal: StrategySignal | None = None,
) -> str | None:
    """
    Returns a rejection reason if any live-trading guardrail fails.
    Returns None when live execution is allowed.
    """

    # ------------------------------------------------------------------
    # HTTPS
    # ------------------------------------------------------------------
    if not _request_is_https(request) and not _allow_insecure_live():
        return "Live trading requires HTTPS."

    # ------------------------------------------------------------------
    # Feature flags
    # ------------------------------------------------------------------
    if not settings.broker_live_enabled:
        return "Live trading requires BROKER_LIVE_ENABLED=true."

    if not settings.risk_engine_enabled:
        return "Live trading requires risk engine enabled."

    # ------------------------------------------------------------------
    # Market data provider
    # ------------------------------------------------------------------
    if (
        getattr(settings, "market_data_provider", None) == "yahoo"
        and not getattr(settings, "allow_yahoo_for_live", False)
    ):
        return (
            "Live trading requires trading-grade market data. "
            "Yahoo is supported only for paper/demo trading."
        )

    # ------------------------------------------------------------------
    # Kill switch
    # ------------------------------------------------------------------
    halt = kill_switch_status()

    if halt.get("active", False):
        return f"Trading halted: {halt.get('reason') or 'Kill switch active'}"

    # ------------------------------------------------------------------
    # Broker circuit breaker
    # ------------------------------------------------------------------
    circuit = broker_circuit_status()

    if circuit.get("active", False):
        return (
            f"Broker circuit breaker active: "
            f"{circuit.get('reason') or 'Broker unavailable'}"
        )

    # ------------------------------------------------------------------
    # Market validation
    # ------------------------------------------------------------------
    market_validation = validate_live_candle(
        candles_1m,
        interval="1m",
        mode="live",
    )

    if (
        not market_validation.valid_for_execution
        or str(market_validation.market_status).upper() != "LIVE MARKET"
    ):
        return (
            "Live trading requires fresh market data. "
            f"Current status: {market_validation.market_status}"
        )

    # ------------------------------------------------------------------
    # Role validation
    # ------------------------------------------------------------------
    if actor.role not in {"admin", "trader"}:
        return "Live trading requires Trader or Admin role."

    # ------------------------------------------------------------------
    # Broker configuration
    # ------------------------------------------------------------------
    if not settings.broker_configured:
        return "Live trading requires broker credentials."

    # ------------------------------------------------------------------
    # Broker session
    # ------------------------------------------------------------------
    try:
        if not _broker_session_valid(settings):
            return "Live trading requires a valid broker session."
    except Exception as exc:
        return f"Broker session validation failed: {exc}"

    # ------------------------------------------------------------------
    # Risk engine
    # ------------------------------------------------------------------
    if not risk_decision.allowed:
        return f"Risk engine rejected trade: {risk_decision.reason}"

    details = getattr(risk_decision, "details", {}) or {}

    daily_pnl = float(details.get("daily_pnl") or 0.0)
    max_daily_loss = float(details.get("max_daily_loss") or 0.0)

    daily_loss = max(0.0, -daily_pnl)

    if max_daily_loss > 0 and daily_loss >= max_daily_loss:
        return "Live trading blocked: maximum daily loss reached."

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------
    if not settings.audit_logging_enabled:
        return "Live trading requires audit logging enabled."

    # ------------------------------------------------------------------
    # Stop protection
    # ------------------------------------------------------------------
    stop_failure = _live_stop_protection_failure(signal)

    if stop_failure:
        return stop_failure

    # ------------------------------------------------------------------
    # Passed all guardrails
    # ------------------------------------------------------------------
    return None
 