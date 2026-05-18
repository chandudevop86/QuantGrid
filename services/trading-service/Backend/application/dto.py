from __future__ import annotations

from dataclasses import asdict
from typing import Any

from Backend.domain.models.signal import StrategySignal



def serialize_signal(signal: StrategySignal) -> dict[str, Any]:
    signal_time = signal.signal_time.isoformat()
    return {
        **asdict(signal),
        "signal_time": signal_time,
        "entry": signal.entry_price,
        "target": signal.target_price,
        "timestamp": signal_time,
        "score": signal.metadata.get("score", signal.metadata.get("total_score")),
        "reason": signal.metadata.get("reason"),
        "data_source": signal.metadata.get("data_source", "cached"),
    }
