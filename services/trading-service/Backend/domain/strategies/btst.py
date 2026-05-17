from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.domain.strategies.base import BaseStrategy, StrategyConfig
from Backend.domain.strategies.signal_builder import SignalBuilder


@dataclass(slots=True)
class BTSTConfig(StrategyConfig):
    lookback: int = 12
    min_score: float = 7.0


class BTSTStrategy(BaseStrategy):
    name = "BTST"

    def __init__(self, config: BTSTConfig | None = None) -> None:
        super().__init__(config or BTSTConfig())
        self.config: BTSTConfig
        self.signal_builder = SignalBuilder()

    def prepare_data(self, data):
        candles = super().prepare_data(data)
        if candles.empty:
            return candles
        out = candles.copy()
        lookback = int(self.config.lookback)
        out["btst_high"] = out["high"].shift(1).rolling(lookback, min_periods=lookback // 2).max()
        out["btst_low"] = out["low"].shift(1).rolling(lookback, min_periods=lookback // 2).min()
        out["avg_volume"] = out["volume"].shift(1).rolling(lookback, min_periods=lookback // 2).mean()
        return out

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        latest_signal: StrategySignal | None = None
        for index in range(int(self.config.lookback), len(candles)):
            row = candles.iloc[index]
            for side in ("BUY", "SELL"):
                score = self._score(row, side)
                if score < float(self.config.min_score):
                    continue
                stop_loss, target_price = self.calculate_levels(candles, index, side, context)
                signal = self.signal_builder.build(
                    row,
                    strategy_name=self.name,
                    symbol=context.symbol,
                    side=side,
                    capital=context.capital,
                    risk_pct=context.risk_pct,
                    stop_loss=stop_loss,
                    target_price=target_price,
                    score=score,
                    metadata={"setup": "btst_momentum_continuation"},
                )
                if signal is not None:
                    latest_signal = signal
                    break
        return [latest_signal] if latest_signal is not None else []

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        row = candles.iloc[index]
        close = float(row["close"])
        buffer = max(float(row["avg_range_5"]) * 0.2, close * 0.001, 0.05)
        if side == "BUY":
            stop_loss = min(float(row["low"]), float(row["btst_high"])) - buffer
            return stop_loss, close + (close - stop_loss) * float(context.rr_ratio)

        stop_loss = max(float(row["high"]), float(row["btst_low"])) + buffer
        return stop_loss, close - (stop_loss - close) * float(context.rr_ratio)

    def _score(self, row: pd.Series, side: str) -> float:
        close = float(row["close"])
        volume_ok = float(row["volume"]) >= float(row["avg_volume"])
        if side == "BUY":
            trend_ok = float(row["ema_9"]) > float(row["ema_21"]) > float(row["ema_50"]) > float(row["ema_200"])
            momentum_ok = float(row["rsi"]) > 55 and float(row["macd"]) > float(row["macd_signal"])
            breakout_ok = close > float(row["btst_high"])
            above_vwap = close >= float(row["vwap"])
            score = 0.0
            score += 2.0 if trend_ok else 0.0
            score += 2.0 if momentum_ok else 0.0
            score += 2.0 if breakout_ok else 0.0
            score += 1.0 if above_vwap else 0.0
            score += 1.0 if volume_ok else 0.0
            return score

        trend_ok = float(row["ema_9"]) < float(row["ema_21"]) < float(row["ema_50"]) < float(row["ema_200"])
        momentum_ok = float(row["rsi"]) < 45 and float(row["macd"]) < float(row["macd_signal"])
        breakout_ok = close < float(row["btst_low"])
        below_vwap = close <= float(row["vwap"])
        score = 0.0
        score += 2.0 if trend_ok else 0.0
        score += 2.0 if momentum_ok else 0.0
        score += 2.0 if breakout_ok else 0.0
        score += 1.0 if below_vwap else 0.0
        score += 1.0 if volume_ok else 0.0
        return score
