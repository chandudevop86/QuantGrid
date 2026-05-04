from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.domain.models.signal import StrategySignal


def serialize_signal(signal: StrategySignal) -> dict[str, Any]:
    payload = asdict(signal)
    payload["signal_time"] = signal.signal_time.isoformat()
    return payload
