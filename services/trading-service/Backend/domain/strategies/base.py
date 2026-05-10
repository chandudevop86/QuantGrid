from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List

import pandas as pd

from Backend.domain.models.signal import StrategySignal
from Backend.domain.models.context import StrategyContext


@dataclass(slots=True)
class StrategyConfig:
    mode: str = "Balanced"
    max_trades_per_day: int = 1
    duplicate_signal_cooldown_bars: int = 12


class BaseStrategy(ABC):
    name = "BaseStrategy"

    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig()

    def run(self, data: Any, context: StrategyContext) -> List[StrategySignal]:
        candles = self.prepare_data(data)
        if candles.empty:
            return []
        return self.generate_signals(candles, context)

    def prepare_data(self, data: Any) -> pd.DataFrame:
        if isinstance(data, pd.DataFrame):
            return data
        return pd.DataFrame(data)

    @abstractmethod
    def generate_signals(
        self, candles: pd.DataFrame, context: StrategyContext
    ) -> List[StrategySignal]:
        pass

    @abstractmethod
    def calculate_levels(
        self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext
    ) -> tuple[float, float]:
        pass
    from typing import Dict


