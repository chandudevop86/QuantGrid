from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.domain.models.context import StrategyContext
from app.domain.models.signal import StrategySignal
from app.domain.strategies.base import BaseStrategy, StrategyConfig
from app.domain.strategies.scoring import ScoringEngine
from app.domain.strategies.signal_builder import SignalBuilder


@dataclass(slots=True)
class MeanReversionConfig(StrategyConfig):
    rsi_lower: float = 30.0
    rsi_upper: float = 70.0
    min_score: float = 3.0


class MeanReversionStrategy(BaseStrategy):
    name = "Mean Reversion"

    def __init__(self, config: MeanReversionConfig | None = None) -> None:
        super().__init__(config or MeanReversionConfig())
        self.config: MeanReversionConfig
        self.scoring = ScoringEngine()
        self.signal_builder = SignalBuilder()

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        signals: list[StrategySignal] = []
        last_signal_index = {"BUY": -10_000, "SELL": -10_000}
        for index in range(20, len(candles)):
            row = candles.iloc[index]
            for side in ("BUY", "SELL"):
                if index - last_signal_index[side] < int(self.config.duplicate_signal_cooldown_bars):
                    continue
                score = self._score(row, side)
                if not self.scoring.passed(score, self.config.min_score):
                    continue
                stop_loss, target_price = self.calculate_levels(candles, index, side, context)
                signal = self.signal_builder.build(row, strategy_name=self.name, symbol=context.symbol, side=side, capital=context.capital, risk_pct=context.risk_pct, stop_loss=stop_loss, target_price=target_price, score=score, metadata={"setup": "oversold_reversion" if side == "BUY" else "overbought_reversion"})
                if signal is not None:
                    signals.append(signal)
                    last_signal_index[side] = index
                    break
        return signals

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        row = candles.iloc[index]
        close = float(row["close"])
        buffer = max(float(row["avg_range_5"]) * 0.5, close * 0.001, 0.05)
        if side.upper() == "BUY":
            stop_loss = float(row["low"]) - buffer
            target_price = min(float(row["ema_21"]), close + (close - stop_loss) * float(context.rr_ratio))
            if target_price <= close:
                target_price = close + (close - stop_loss) * float(context.rr_ratio)
            return stop_loss, target_price
        stop_loss = float(row["high"]) + buffer
        target_price = max(float(row["ema_21"]), close - (stop_loss - close) * float(context.rr_ratio))
        if target_price >= close:
            target_price = close - (stop_loss - close) * float(context.rr_ratio)
        return stop_loss, target_price

    def _score(self, row: pd.Series, side: str) -> float:
        if side == "BUY":
            score = 2.0 if float(row["rsi"]) <= float(self.config.rsi_lower) else 0.0
            score += 1.0 if float(row["close"]) < float(row["ema_21"]) else 0.0
            score += 1.0 if float(row["macd_hist"]) > 0.0 else 0.0
            return score
        score = 2.0 if float(row["rsi"]) >= float(self.config.rsi_upper) else 0.0
        score += 1.0 if float(row["close"]) > float(row["ema_21"]) else 0.0
        score += 1.0 if float(row["macd_hist"]) < 0.0 else 0.0
        return score
