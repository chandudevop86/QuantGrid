from __future__ import annotations

from typing import Any


def analyze_delivery(delivery_data: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not delivery_data:
        return {
            "delivery_percentage": None,
            "delivery_signal": "UNKNOWN",
            "reason": "Delivery data was not provided.",
        }
    latest = delivery_data[-1]
    delivery_percentage = _delivery_percentage(latest)
    if delivery_percentage is None:
        return {
            "delivery_percentage": None,
            "delivery_signal": "UNKNOWN",
            "reason": "Delivery percentage could not be calculated from the supplied data.",
        }
    if delivery_percentage >= 55:
        signal = "ACCUMULATION"
        reason = "High delivery percentage suggests committed buying participation."
    elif delivery_percentage <= 35:
        signal = "DISTRIBUTION"
        reason = "Low delivery percentage suggests weaker holding conviction."
    else:
        signal = "NEUTRAL"
        reason = "Delivery percentage is near normal range."
    return {
        "delivery_percentage": round(delivery_percentage, 2),
        "delivery_signal": signal,
        "reason": reason,
    }


def _delivery_percentage(row: dict[str, Any]) -> float | None:
    for key in ("delivery_percentage", "delivery_percent", "delivery_pct"):
        if row.get(key) is not None:
            return float(row[key])
    delivered = row.get("delivered_quantity")
    traded = row.get("traded_quantity") or row.get("volume")
    if delivered is not None and traded:
        return float(delivered) / max(float(traded), 1.0) * 100.0
    return None
