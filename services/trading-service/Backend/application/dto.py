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
    payload["timestamp"] = payload["signal_time"]
    for key in ("amd_phase", "fvg_zone", "zone_type", "zone", "htf_bias", "trend", "reason"):
        if key in signal.metadata:
            payload[key] = signal.metadata[key]
    return payload
