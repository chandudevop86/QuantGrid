from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from Backend.application.paper_trade_store import risk_status
from Backend.application.signal_quality import SignalDecision


@dataclass(frozen=True, slots=True)
class RiskGateResult:
    allowed: bool
    reason: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_risk_gate(decision: SignalDecision) -> RiskGateResult:
    if not decision.allowed:
        return RiskGateResult(False, decision.reason, decision.to_dict())

    status = risk_status()
    if abs(min(0.0, float(status["daily_pnl"]))) >= float(status["max_daily_loss"]):
        return RiskGateResult(False, "DAILY_LOSS_LIMIT", status)
    if int(status["trades_today"]) >= int(status["max_trades_per_day"]):
        return RiskGateResult(False, "MAX_TRADES_PER_DAY", status)
    if int(status["consecutive_losses"]) >= int(status["max_consecutive_losses"]):
        return RiskGateResult(False, "MAX_CONSECUTIVE_LOSSES", status)

    return RiskGateResult(True, "OK", status)
