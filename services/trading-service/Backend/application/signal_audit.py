from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from Backend.application.dto import serialize_signal
from Backend.application.risk_gate import evaluate_risk_gate, validate_order_risk
from Backend.application.signal_quality import decide_signal
from Backend.application.signal_validation import MIN_RISK_REWARD
from Backend.domain.models.signal import StrategySignal


AUDIT_STRATEGIES: tuple[tuple[str, str], ...] = (
    ("amd", "AMD"),
    ("breakout", "Breakout"),
    ("btst", "BTST"),
    ("cbt", "CBT"),
    ("crt_tbs", "CRT TBS"),
    ("mean_reversion", "Mean Reversion"),
    ("mtf", "MTF"),
    ("mtfa", "MTFA"),
    ("supply_demand", "Supply Demand"),
)

REJECTION_REASONS = {
    "NEUTRAL",
    "LOW_CONFIDENCE",
    "MISSING_RISK_REWARD",
    "STALE_CANDLE",
    "MARKET_CLOSED",
    "RISK_REJECTED",
    "MAX_TRADES_REACHED",
    "MISSING_STOP_LOSS",
    "MISSING_TARGET",
}

logger = logging.getLogger("quantgrid.signal_audit")


@dataclass(slots=True)
class StrategyAuditInput:
    key: str
    label: str
    raw_signals: list[StrategySignal]
    validated_signals: list[StrategySignal]
    candles: list[dict[str, Any]]
    trend_candles: list[dict[str, Any]]
    candle_source: str | None
    candle_validation: Any
    execution_mode: str = "paper"
    paper_trade_created_count: int = 0


def risk_reward(signal: StrategySignal | None) -> float | None:
    if signal is None:
        return None
    risk = abs(float(signal.entry_price) - float(signal.stop_loss or 0))
    if risk <= 0:
        return None
    return round(abs(float(signal.target_price or 0) - float(signal.entry_price)) / risk, 2)


def signal_confidence(signal: StrategySignal | None) -> float | None:
    if signal is None:
        return None
    score = signal.metadata.get("score", signal.metadata.get("total_score", 0))
    try:
        return min(100.0, round(float(score) * 10, 1))
    except (TypeError, ValueError):
        return 0.0


def normalize_rejection_reason(reason: str | None, signal: StrategySignal | None = None) -> str:
    raw = str(reason or "").upper()
    if signal is None and not raw:
        return "NEUTRAL"
    if signal is not None:
        if signal.stop_loss is None or float(signal.stop_loss or 0) <= 0:
            return "MISSING_STOP_LOSS"
        if signal.target_price is None or float(signal.target_price or 0) <= 0:
            return "MISSING_TARGET"
        rr = risk_reward(signal)
        if rr is None or rr < MIN_RISK_REWARD:
            return "MISSING_RISK_REWARD"
    if not raw or raw in {"OK", "ACCEPTED"}:
        return "NEUTRAL"
    if "LOW" in raw or "SCORE" in raw or "CONFIDENCE" in raw or "WEAK" in raw:
        return "LOW_CONFIDENCE"
    if "STALE" in raw or "CANDLE" in raw or "DELAYED" in raw:
        return "STALE_CANDLE"
    if "MARKET" in raw and ("CLOSED" in raw or "NOT_LIVE" in raw or "NOT LIVE" in raw):
        return "MARKET_CLOSED"
    if "MAX_TRADES" in raw or "MAX TRADES" in raw or "TRADES_PER_DAY" in raw:
        return "MAX_TRADES_REACHED"
    if "STOP" in raw:
        return "MISSING_STOP_LOSS"
    if "TARGET" in raw:
        return "MISSING_TARGET"
    if "RISK" in raw or "LOSS" in raw or "KILL" in raw or "QUANTITY" in raw or "MARGIN" in raw:
        return "RISK_REJECTED"
    return "RISK_REJECTED"


def audit_strategy(item: StrategyAuditInput) -> dict[str, Any]:
    latest_signal = item.validated_signals[0] if item.validated_signals else (item.raw_signals[0] if item.raw_signals else None)
    rejected_count = max(0, len(item.raw_signals) - len(item.validated_signals))
    rejection_reason: str | None = None
    execution_decision = "NO_RAW_SIGNAL"
    accepted_count = 0

    if not item.raw_signals:
        rejection_reason = "NEUTRAL"
    elif not item.validated_signals:
        diagnostics_reason = _first_validation_rejection(item.raw_signals, item.candles, item.candle_source)
        rejection_reason = normalize_rejection_reason(diagnostics_reason, latest_signal)
        rejected_count = len(item.raw_signals)
        execution_decision = "REJECTED_SIGNAL"
    else:
        decision = decide_signal(latest_signal, candles_1m=item.candles, candles_15m=item.trend_candles)
        gate = evaluate_risk_gate(decision)
        risk_decision = validate_order_risk(latest_signal, execution_mode=item.execution_mode, candles_1m=item.candles)
        market_status = str(getattr(item.candle_validation, "market_status", "LIVE MARKET"))
        if not getattr(item.candle_validation, "valid_for_execution", False) or market_status.upper() != "LIVE MARKET":
            rejection_reason = normalize_rejection_reason(f"MARKET_NOT_LIVE_FOR_EXECUTION: {market_status}", latest_signal)
            execution_decision = "BLOCKED_MARKET"
        elif not decision.allowed:
            rejection_reason = normalize_rejection_reason(decision.reason, latest_signal)
            execution_decision = "REJECTED_SIGNAL"
        elif not gate.allowed:
            rejection_reason = normalize_rejection_reason(gate.reason, latest_signal)
            execution_decision = "RISK_REJECTED"
        elif not risk_decision.allowed:
            rejection_reason = normalize_rejection_reason(risk_decision.reason, latest_signal)
            execution_decision = "RISK_REJECTED"
        else:
            accepted_count = 1
            execution_decision = "READY_FOR_PAPER_TRADE"

    payload = {
        "strategy": item.label,
        "strategy_key": item.key,
        "raw_signal_count": len(item.raw_signals),
        "validated_signal_count": len(item.validated_signals),
        "accepted_signal_count": accepted_count,
        "rejected_signal_count": rejected_count if rejection_reason else 0,
        "paper_trade_created_count": item.paper_trade_created_count,
        "latest_signal": latest_signal.side if latest_signal else "NEUTRAL",
        "confidence": signal_confidence(latest_signal),
        "risk_reward": risk_reward(latest_signal),
        "rejection_reason": rejection_reason,
        "last_run_time": latest_signal.signal_time.isoformat() if latest_signal else None,
        "execution_decision": execution_decision,
        "lifecycle": {
            "RAW_SIGNAL": len(item.raw_signals),
            "VALIDATED_SIGNAL": len(item.validated_signals),
            "ACCEPTED_SIGNAL": accepted_count,
            "REJECTED_SIGNAL": rejected_count if rejection_reason else 0,
            "PAPER_TRADE_CREATED": item.paper_trade_created_count,
        },
    }
    logger.info(
        "strategy_signal_audit",
        extra={
            "strategy_name": item.label,
            "candles_count": len(item.candles),
            "raw_signal": len(item.raw_signals),
            "validated_signal": len(item.validated_signals),
            "rejected_reason": rejection_reason,
            "execution_decision": execution_decision,
        },
    )
    if latest_signal is not None:
        payload["latest_signal_payload"] = serialize_signal(latest_signal)
    return payload


def _first_validation_rejection(signals: list[StrategySignal], candles: list[dict[str, Any]], candle_source: str | None) -> str | None:
    for signal in signals:
        rr = risk_reward(signal)
        if rr is None or rr < MIN_RISK_REWARD:
            return "MISSING_RISK_REWARD"
        if signal_confidence(signal) is not None and float(signal_confidence(signal) or 0) < 70:
            return "LOW_CONFIDENCE"
    return "LOW_CONFIDENCE"
