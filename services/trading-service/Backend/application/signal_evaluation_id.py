"""Stable diagnostic identifier for a single market-context signal decision.

Not an order idempotency key: no trading permission or execution side effects.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def signal_evaluation_id(signal: dict[str, Any], decision: dict[str, Any], latest_candle: Any) -> str:
    metadata = signal.get("metadata") or {}
    key = {
        "strategy": signal.get("strategy_name"),
        "symbol": signal.get("symbol"),
        "side": signal.get("signal") or signal.get("side"),
        "signal_time": signal.get("timestamp") or signal.get("signal_time"),
        "entry": signal.get("entry_price") or signal.get("entry"),
        "stop": signal.get("stop_loss"),
        "target": signal.get("target_price") or signal.get("target"),
        "latest_candle": str(latest_candle),
        "decision": decision.get("status"),
        "reason": decision.get("reason"),
        "mtf_bias": decision.get("mtf_bias") or metadata.get("mtf_bias"),
    }
    payload = json.dumps(key, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
