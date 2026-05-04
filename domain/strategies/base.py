from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.domain.indicators.indicators import IndicatorService
from app.domain.models.context import StrategyContext
from app.domain.models.signal import StrategySignal


@dataclass(slots=True)
class StrategyConfig:
    mode: str = "Balanced"
    max_trades_per_day: int = 1
    duplicate_signal_cooldown_bars: int = 12


class BaseStrategy(ABC):
    name = "Base Strategy"

    def __init__(self, config: StrategyConfig | None = None, indicators: IndicatorService | None = None) -> None:
        self.config = config or StrategyConfig()
        self.indicators = indicators or IndicatorService()

    def run(self, data: Any, context: StrategyContext) -> list[StrategySignal]:
        candles = self.prepare_data(data)
        if candles.empty:
            return []
        return self.generate_signals(candles, context)

    def prepare_data(self, data: Any) -> pd.DataFrame:
        return self.indicators.prepare(data)

    @abstractmethod
    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        raise NotImplementedError

    @abstractmethod
    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        raise NotImplementedError


def normalize_mode(mode: str) -> str:
    raw = str(mode or "").strip().lower()
    if raw == "conservative":
        return "Conservative"
    if raw == "aggressive":
        return "Aggressive"
    return "Balanced"


def recent_true(series: pd.Series, index: int, lookback: int) -> int | None:
    left = max(0, int(index) - int(lookback))
    window = series.iloc[left : index + 1]
    matches = window[window.fillna(False)]
    if matches.empty:
        return None
    return int(matches.index[-1])
