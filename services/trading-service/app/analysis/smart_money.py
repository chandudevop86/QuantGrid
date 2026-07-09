from __future__ import annotations

from typing import Any

from Backend.application.volume_analysis import analyze_volume


def analyze_smart_money(
    *,
    symbol: str,
    timeframe: str,
    candles: list[dict[str, Any]],
    delivery_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = analyze_volume(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        delivery_data=delivery_data,
    ).to_dict()
    return {
        "smart_money_score": result["smart_money_score"],
        "volume_confidence": result["volume_confidence"],
        "institutional_buying": result["institutional_buying"],
        "institutional_selling": result["institutional_selling"],
        "signal": result["signal"],
        "reason": result["reason"],
    }
