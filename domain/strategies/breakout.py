from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.domain.models.context import StrategyContext
from app.domain.models.signal import StrategySignal
from app.domain.strategies.base import BaseStrategy, StrategyConfig
from app.domain.strategies.scoring import ScoringEngine
from app.domain.strategies.signal_builder import SignalBuilder


@dataclass(slots=True)
class BreakoutConfig(StrategyConfig):
    lookback: int = 20
    min_score: float = 3.0


class BreakoutStrategy(BaseStrategy):
    name = "Breakout"

    def __init__(self, config: BreakoutConfig | None = None) -> None:
        super().__init__(config or BreakoutConfig())
        self.config: BreakoutConfig
        self.scoring = ScoringEngine()
        self.signal_builder = SignalBuilder()

    def prepare_data(self, data: Any) -> pd.DataFrame:
        candles = super().prepare_data(data)
        if candles.empty:
            return candles
        lookback = int(self.config.lookback)
        out = candles.copy()
        out["breakout_high"] = out["high"].shift(1).rolling(lookback, min_periods=lookback // 2).max()
        out["breakout_low"] = out["low"].shift(1).rolling(lookback, min_periods=lookback // 2).min()
        out["avg_volume"] = out["volume"].shift(1).rolling(lookback, min_periods=lookback // 2).mean()
        return out

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        signals: list[StrategySignal] = []
        last_signal_index = {"BUY": -10_000, "SELL": -10_000}
        for index in range(int(self.config.lookback), len(candles)):
            row = candles.iloc[index]
            for side in ("BUY", "SELL"):
                if index - last_signal_index[side] < int(self.config.duplicate_signal_cooldown_bars):
                    continue
                score = self._score(row, side)
                if not self.scoring.passed(score, self.config.min_score):
                    continue
                stop_loss, target_price = self.calculate_levels(candles, index, side, context)
                signal = self.signal_builder.build(row, strategy_name=self.name, symbol=context.symbol, side=side, capital=context.capital, risk_pct=context.risk_pct, stop_loss=stop_loss, target_price=target_price, score=score, metadata={"breakout_type": "range_high" if side == "BUY" else "range_low"})
                if signal is not None:
                    signals.append(signal)
                    last_signal_index[side] = index
                    break
        return signals

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        row = candles.iloc[index]
        close = float(row["close"])
        buffer = max(float(row["avg_range_5"]) * 0.25, close * 0.001, 0.05)
        if side.upper() == "BUY":
            stop_loss = min(float(row["low"]), float(row["breakout_high"])) - buffer
            return stop_loss, close + (close - stop_loss) * float(context.rr_ratio)
        stop_loss = max(float(row["high"]), float(row["breakout_low"])) + buffer
        return stop_loss, close - (stop_loss - close) * float(context.rr_ratio)

    def _score(self, row: pd.Series, side: str) -> float:
        if side == "BUY":
            score = 2.0 if float(row["close"]) > float(row["breakout_high"]) else 0.0
            score += 1.0 if float(row["close"]) >= float(row["vwap"]) else 0.0
            score += 1.0 if float(row["volume"]) >= float(row["avg_volume"]) else 0.0
            return score
        score = 2.0 if float(row["close"]) < float(row["breakout_low"]) else 0.0
        score += 1.0 if float(row["close"]) <= float(row["vwap"]) else 0.0
        score += 1.0 if float(row["volume"]) >= float(row["avg_volume"]) else 0.0
        return score
