from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone as UTC
from typing import Any


@dataclass(slots=True)
class TimeframeTrend:
    timeframe: str                  # 1m,5m,15m,1h...
    trend: str                      # BULLISH / BEARISH / SIDEWAYS
    confidence: float               # 0-100

    ema_alignment: bool = False
    market_structure: str = ""

    adx: float = 0.0
    atr: float = 0.0
    rsi: float = 0.0
    macd_signal: str = ""

    volume_confirmation: bool = False
    breakout: bool = False

    support: float | None = None
    resistance: float | None = None

    score: float = 0.0

    trend_strength: float = 0.0

    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MarketRegime:
    regime: str                     # TRENDING / RANGING / BREAKOUT / REVERSAL
    bias: str                       # STRONG_BULLISH / BULLISH / NEUTRAL / BEARISH
    confidence: float               # 0-100

    recommended_strategy: str

    allowed_strategies: list[str] = field(default_factory=list)
    blocked_strategies: list[str] = field(default_factory=list)

    overall_score: float = 0.0

    timeframe_alignment: float = 0.0
    volatility_score: float = 0.0
    liquidity_score: float = 0.0

    trend_strength: float = 0.0

    execution_allowed: bool = False

    primary_timeframe: str = "15m"
    confirmation_timeframe: str = "5m"

    warnings: list[str] = field(default_factory=list)

    generated_at: datetime = field(default_factory=datetime.utcnow)

    diagnostics: dict[str, Any] = field(default_factory=dict)