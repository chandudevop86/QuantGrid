from __future__ import annotations

from dataclasses import asdict
from typing import Any

from Backend.domain.models.signal import StrategySignal



def serialize_signal(signal: StrategySignal) -> dict[str, Any]:
    return {
        **asdict(signal),
        "signal_time": signal.signal_time.isoformat(),
    }