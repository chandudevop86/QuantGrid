from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.domain.strategies.base import BaseStrategy, StrategyConfig
from Backend.domain.strategies.signal_builder import SignalBuilder


@dataclass(slots=True)
class SupplyDemandConfig(StrategyConfig):
    zone_lookback: int = 20
    min_score: float = 7.0


class SupplyDemandStrategy(BaseStrategy):
    name = "Supply Demand"

    def __init__(self, config: SupplyDemandConfig | None = None) -> None:
        super().__init__(config or SupplyDemandConfig())
        self.config: SupplyDemandConfig
        self.signal_builder = SignalBuilder()

    def prepare_data(self, data):
        candles = super().prepare_data(data)
        if candles.empty:
            return candles
        out = candles.copy()
        lookback = int(self.config.zone_lookback)
        out["demand_zone"] = out["low"].shift(1).rolling(lookback, min_periods=lookback // 2).min()
        out["supply_zone"] = out["high"].shift(1).rolling(lookback, min_periods=lookback // 2).max()
        return out

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        latest_signal: StrategySignal | None = None
        for index in range(int(self.config.zone_lookback), len(candles)):
            row = candles.iloc[index]
            for side in ("BUY", "SELL"):
                score = self._score(row, side)
                if score < float(self.config.min_score):
                    continue
                stop_loss, target_price = self.calculate_levels(candles, index, side, context)
                metadata = {
                    "zone_type": "demand" if side == "BUY" else "supply",
                    "setup": "demand_rejection" if side == "BUY" else "supply_rejection",
                }
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
                    metadata=metadata,
                )
                if signal is not None:
                    latest_signal = signal
                    break
        return [latest_signal] if latest_signal is not None else []

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        row = candles.iloc[index]
        close = float(row["close"])
        buffer = max(float(row["avg_range_5"]) * 0.25, close * 0.001, 0.05)
        if side == "BUY":
            stop_loss = min(float(row["low"]), float(row["demand_zone"])) - buffer
            return stop_loss, close + (close - stop_loss) * float(context.rr_ratio)

        stop_loss = max(float(row["high"]), float(row["supply_zone"])) + buffer
        return stop_loss, close - (stop_loss - close) * float(context.rr_ratio)

    def _score(self, row: pd.Series, side: str) -> float:
        close = float(row["close"])
        open_price = float(row["open"])
        bar_range = max(float(row["bar_range"]), 0.01)
        body_size = float(row["body_size"])
        avg_range = max(float(row["avg_range_5"]), 0.01)
        rsi = float(row["rsi"])
        macd = float(row["macd"])
        macd_signal = float(row["macd_signal"])

        if side == "BUY":
            zone = float(row["demand_zone"])
            touched_zone = float(row["low"]) <= zone + avg_range * 0.3
            rejected_zone = close > open_price and close > zone
            trend_ok = float(row["ema_9"]) > float(row["ema_21"]) > float(row["ema_50"]) > float(row["ema_200"])
            momentum_ok = rsi > 40 and macd > macd_signal
            score = 0.0
            score += 2.0 if touched_zone else 0.0
            score += 2.0 if rejected_zone else 0.0
            score += 2.0 if trend_ok else 0.0
            score += 2.0 if momentum_ok else 0.0
            score += 1.0 if body_size >= bar_range * 0.45 else 0.0
            return score

        zone = float(row["supply_zone"])
        touched_zone = float(row["high"]) >= zone - avg_range * 0.3
        rejected_zone = close < open_price and close < zone
        trend_ok = float(row["ema_9"]) < float(row["ema_21"]) < float(row["ema_50"]) < float(row["ema_200"])
        momentum_ok = rsi < 60 and macd < macd_signal
        score = 0.0
        score += 2.0 if touched_zone else 0.0
        score += 2.0 if rejected_zone else 0.0
        score += 2.0 if trend_ok else 0.0
        score += 2.0 if momentum_ok else 0.0
        score += 1.0 if body_size >= bar_range * 0.45 else 0.0
        return score
