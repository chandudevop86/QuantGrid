from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VolumeAnalysisRequest(BaseModel):
    symbol: str = "NIFTY"
    timeframe: str = "1m"
    candles: list[dict[str, Any]] = Field(default_factory=list)
    delivery_data: list[dict[str, Any]] | None = None


class VolumeAnalysisResponse(BaseModel):
    symbol: str
    timeframe: str
    current_volume: float
    average_volume_20: float
    average_volume_50: float
    volume_ratio: float
    relative_volume: float
    volume_trend: str
    delivery_percentage: float | None
    volume_spike: bool
    breakout_confirmation: bool
    breakdown_confirmation: bool
    accumulation: bool
    distribution: bool
    institutional_buying: bool
    institutional_selling: bool
    obv: float
    vwap: float
    cmf: float
    ad_line: float
    volume_profile: dict[str, Any]
    smart_money_score: int
    volume_confidence: int
    signal: str
    reason: str
    ai_summary: str
