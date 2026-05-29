from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from Backend.application.candle_validation import validate_live_candle
from Backend.application.kill_switch import kill_switch_status
from Backend.application.paper_trade_store import risk_status
from Backend.application.signal_quality import SignalDecision
from Backend.domain.execution_constraints import requested_quantity
from Backend.domain.models.signal import StrategySignal


@dataclass(frozen=True, slots=True)
class RiskGateResult:
    allowed: bool
    reason: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OrderRiskDecision:
    allowed: bool
    reason: str
    risk_amount: float
    max_allowed_risk: float
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_risk_gate(decision: SignalDecision) -> RiskGateResult:
    if not decision.allowed:
        return RiskGateResult(False, decision.reason, decision.to_dict())

    kill_switch = kill_switch_status()
    if kill_switch["active"]:
        return RiskGateResult(False, "KILL_SWITCH_ACTIVE", kill_switch)

    status = risk_status()
    if abs(min(0.0, float(status["daily_pnl"]))) >= float(status["max_daily_loss"]):
        return RiskGateResult(False, "DAILY_LOSS_LIMIT", status)
    if int(status["trades_today"]) >= int(status["max_trades_per_day"]):
        return RiskGateResult(False, "MAX_TRADES_PER_DAY", status)
    if int(status["consecutive_losses"]) >= int(status["max_consecutive_losses"]):
        return RiskGateResult(False, "MAX_CONSECUTIVE_LOSSES", status)

    return RiskGateResult(True, "OK", status)


def validate_order_risk(
    signal: StrategySignal,
    *,
    execution_mode: str,
    candles_1m: list[dict[str, Any]] | None = None,
) -> OrderRiskDecision:
    status = risk_status()
    kill_switch = kill_switch_status()
    quantity = requested_quantity(signal)
    max_quantity = int(status["max_quantity"])
    risk_amount = _risk_amount(signal, quantity)
    max_allowed_risk = round(float(status["risk_per_trade_amount"]), 2)

    def decision(allowed: bool, reason: str, extra: dict[str, Any] | None = None) -> OrderRiskDecision:
        details = {
            "execution_mode": execution_mode,
            "quantity": quantity,
            "max_quantity": max_quantity,
            "daily_pnl": status["daily_pnl"],
            "max_daily_loss": status["max_daily_loss"],
            "open_positions": status["open_positions"],
            "max_open_positions": status["max_open_positions"],
            "risk_configured": status["risk_configured"],
            "kill_switch_active": kill_switch["active"],
        }
        if extra:
            details.update(extra)
        return OrderRiskDecision(allowed, reason, risk_amount, max_allowed_risk, details)

    if kill_switch["active"]:
        return decision(False, f"KILL_SWITCH_ACTIVE: {kill_switch.get('reason') or 'Trading halted'}", {"kill_switch": kill_switch})
    if execution_mode == "live" and not bool(status["risk_configured"]):
        return decision(False, "LIVE_RISK_CONFIG_MISSING")
    if quantity <= 0:
        return decision(False, "MAX_QUANTITY: quantity must be positive")
    if quantity > max_quantity:
        return decision(False, f"MAX_QUANTITY: requested {quantity}, max {max_quantity}")

    try:
        entry = float(signal.entry_price)
        stop = float(signal.stop_loss)
        target = float(signal.target_price)
    except (TypeError, ValueError):
        return decision(False, "ENTRY_STOP_TARGET_MUST_BE_NUMERIC")

    if stop <= 0:
        return decision(False, "STOP_LOSS_REQUIRED")
    if target <= 0:
        return decision(False, "TARGET_REQUIRED")
    if entry <= 0:
        return decision(False, "ENTRY_REQUIRED")
    if risk_amount <= 0:
        return decision(False, "RISK_AMOUNT_INVALID")
    if risk_amount > max_allowed_risk:
        return decision(False, "MAX_RISK_PER_TRADE_EXCEEDED")
    if abs(min(0.0, float(status["daily_pnl"]))) >= float(status["max_daily_loss"]):
        return decision(False, "MAX_DAILY_LOSS_EXCEEDED")
    if int(status["open_positions"]) >= int(status["max_open_positions"]):
        return decision(False, "MAX_OPEN_POSITIONS_EXCEEDED")

    validation = validate_live_candle(candles_1m or [], interval="1m", mode=execution_mode)
    if not validation.valid_for_execution:
        return decision(
            False,
            f"STALE_MARKET_DATA: {validation.market_status}",
            {"market_validation": validation.model_dump() if hasattr(validation, "model_dump") else validation.__dict__},
        )

    return decision(True, "OK", {"market_validation": validation.model_dump() if hasattr(validation, "model_dump") else validation.__dict__})


def _risk_amount(signal: StrategySignal, quantity: int) -> float:
    try:
        return round(abs(float(signal.entry_price) - float(signal.stop_loss)) * max(0, int(quantity)), 2)
    except (TypeError, ValueError):
        return 0.0
