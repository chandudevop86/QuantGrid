from __future__ import annotations

from typing import Any

from Backend.application.volume_analysis import VolumeAnalysisResult
from Backend.application.volume_analysis import analyze_volume as _analyze_volume


def analyze_volume(
    *,
    symbol: str,
    timeframe: str,
    candles: list[dict[str, Any]],
    delivery_data: list[dict[str, Any]] | None = None,
) -> VolumeAnalysisResult:
    return _analyze_volume(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        delivery_data=delivery_data,
    )
