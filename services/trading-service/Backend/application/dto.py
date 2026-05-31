from __future__ import annotations

from dataclasses import asdict
from typing import Any

from Backend.domain.models.signal import StrategySignal


def serialize_signal(signal: StrategySignal) -> dict[str, Any]:
    payload = asdict(signal)
    payload["signal_time"] = signal.signal_time.isoformat()
    payload["entry"] = signal.entry_price
    payload["target"] = signal.target_price
    payload["score"] = signal.metadata.get("score", signal.metadata.get("total_score"))
    score = float(payload["score"] or 0.0)
    risk = max(abs(float(signal.entry_price) - float(signal.stop_loss)), 1e-9)
    reward = abs(float(signal.target_price) - float(signal.entry_price))
    rr_ratio = reward / risk
    payload["rr_ratio"] = round(rr_ratio, 2)
    payload["confidence_score"] = min(100.0, round(score * 10, 1))
    payload["quality_tier"] = _signal_tier(score, rr_ratio)
    payload["strategy_strength"] = payload["quality_tier"]
    payload["historical_win_rate"] = signal.metadata.get("historical_win_rate", 0.0)
    payload["recent_accuracy"] = signal.metadata.get("recent_accuracy", 0.0)
    payload["timestamp"] = payload["signal_time"]
    for key in (
        "amd_phase",
        "fvg_zone",
        "zone_type",
        "zone",
        "htf_bias",
        "trend",
        "reason",
        "crt_range",
        "liquidity_sweep",
        "trap_type",
        "signal_quality",
        "target_1",
        "target_2",
        "entry_zone",
        "sweep_type",
        "trade_qualification",
        "tqe_score",
        "quality_grade",
        "market_context",
        "volume_status",
        "volatility_status",
        "position_size",
        "risk_amount",
    ):
        if key in signal.metadata:
            payload[key] = signal.metadata[key]
    return payload


def _signal_tier(score: float, rr_ratio: float) -> str:
    if score >= 12 and rr_ratio >= 2.0:
        return "HIGH QUALITY"
    if score >= 9 and rr_ratio >= 1.5:
        return "MEDIUM QUALITY"
    if score >= 6:
        return "WATCHLIST"
    return "REJECTED"
