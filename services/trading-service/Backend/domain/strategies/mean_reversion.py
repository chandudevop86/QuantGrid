from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.domain.strategies.base import BaseStrategy, StrategyConfig
from Backend.domain.strategies.signal_builder import SignalBuilder


@dataclass(slots=True)
class MeanReversionConfig(StrategyConfig):
    rsi_lower: float = 30.0
    rsi_upper: float = 70.0
    min_score: float = 5.0
    min_history_bars: int = 50
    lookback: int = 20
    swing_lookback: int = 6
    cooldown_bars: int = 15
    min_rr: float = 2.0
    min_mean_deviation_pct: float = 0.0012
    strong_breakout_atr: float = 1.25
    max_ema_slope_pct: float = 0.0018
    max_atr_pct: float = 0.004
    volume_lookback: int = 20


@dataclass(frozen=True, slots=True)
class ScoreResult:
    total: float
    components: dict[str, float]
    reason: str


class MeanReversionStrategy(BaseStrategy):
    name = "Mean Reversion"

    def __init__(self, config: MeanReversionConfig | None = None) -> None:
        super().__init__(config or MeanReversionConfig())
        self.config: MeanReversionConfig
        self.signal_builder = SignalBuilder()

    def prepare_data(self, data: Any) -> pd.DataFrame:
        candles = super().prepare_data(data)
        if candles.empty:
            return candles

        out = candles.copy()
        lookback = int(self.config.lookback)
        swing = int(self.config.swing_lookback)
        volume_lookback = int(self.config.volume_lookback)

        out["true_range"] = self._true_range(out)
        out["atr_14"] = out["true_range"].rolling(14, min_periods=5).mean()
        out["avg_volume"] = out["volume"].shift(1).rolling(volume_lookback, min_periods=5).mean()
        out["session_day"] = out["timestamp"].dt.strftime("%Y-%m-%d")
        out["session_high"] = out.groupby("session_day")["high"].cummax().shift(1)
        out["session_low"] = out.groupby("session_day")["low"].cummin().shift(1)
        out["swing_high"] = out["high"].shift(1).rolling(swing, min_periods=2).max()
        out["swing_low"] = out["low"].shift(1).rolling(swing, min_periods=2).min()
        out["range_high"] = out["high"].shift(1).rolling(lookback, min_periods=lookback // 2).max()
        out["range_low"] = out["low"].shift(1).rolling(lookback, min_periods=lookback // 2).min()
        out["ema_50_slope_pct"] = out["ema_50"].diff(5).abs().div(out["close"]).fillna(0.0)
        out["atr_pct"] = out["atr_14"].div(out["close"]).fillna(0.0)
        out["mean_price"] = out[["vwap", "ema_21"]].mean(axis=1)
        out["mean_deviation_pct"] = (out["close"] - out["mean_price"]).abs().div(out["mean_price"]).fillna(0.0)
        return out

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        latest_signal: StrategySignal | None = None
        traded_sessions: set[tuple[str, str]] = set()
        last_signal_index = {"BUY": -10_000, "SELL": -10_000}
        start_index = max(int(self.config.min_history_bars), int(self.config.lookback), int(self.config.volume_lookback))

        for index in range(start_index, len(candles)):
            row = candles.iloc[index]
            session_day = str(row["session_day"])

            if not self._is_ranging_regime(row):
                continue
            if self._is_strong_breakout(candles, index):
                continue

            for side in ("BUY", "SELL"):
                if (session_day, side) in traded_sessions:
                    continue
                if index - last_signal_index[side] < int(self.config.cooldown_bars):
                    continue
                if not self._trend_allows(row, side):
                    continue
                if not self._rsi_extreme(row, side):
                    continue
                if not self._mean_deviation_ok(row):
                    continue
                if not self._confirmation_candle(candles, index, side):
                    continue

                score = self._score(candles, index, side)
                if score.total < float(self.config.min_score):
                    continue

                stop_loss, target_price = self.calculate_levels(candles, index, side, context)
                if not self._risk_reward_ok(row, stop_loss, target_price):
                    continue

                signal = self.signal_builder.build(
                    row,
                    strategy_name=self.name,
                    symbol=context.symbol,
                    side=side,
                    capital=context.capital,
                    risk_pct=1.0,
                    stop_loss=stop_loss,
                    target_price=target_price,
                    score=score.total,
                    metadata={
                        "setup": "enhanced_mean_reversion",
                        "reason": score.reason,
                        "score_components": score.components,
                        "market_regime": "ranging",
                        "trend_filter": "uptrend" if side == "BUY" else "downtrend",
                        "mean_reference": "vwap_ema21",
                        "mean_deviation_pct": round(float(row["mean_deviation_pct"]) * 100, 3),
                        "risk_pct": 1.0,
                        "min_rr": float(self.config.min_rr),
                    },
                )
                if signal is not None:
                    latest_signal = signal
                    traded_sessions.add((session_day, side))
                    last_signal_index[side] = index
                    break

        return [latest_signal] if latest_signal is not None else []

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        row = candles.iloc[index]
        close = float(row["close"])
        atr = self._safe_positive(row.get("atr_14"), fallback=max(float(row["avg_range_5"]), close * 0.001))
        buffer = max(atr * 0.2, close * 0.0005, 0.05)
        rr_ratio = max(float(context.rr_ratio), float(self.config.min_rr))

        if side == "BUY":
            swing_low = self._safe_positive(row.get("swing_low"), fallback=float(row["low"]))
            stop_loss = min(float(row["low"]), swing_low) - buffer
            risk = close - stop_loss
            return stop_loss, close + risk * rr_ratio

        swing_high = self._safe_positive(row.get("swing_high"), fallback=float(row["high"]))
        stop_loss = max(float(row["high"]), swing_high) + buffer
        risk = stop_loss - close
        return stop_loss, close - risk * rr_ratio

    def _score(self, candles: pd.DataFrame, index: int, side: str) -> ScoreResult:
        row = candles.iloc[index]
        components: dict[str, float] = {}

        components["rsi_extreme"] = self._rsi_score(row, side)
        components["mean_deviation"] = self._mean_deviation_score(row)
        components["trend_alignment"] = 3.0 if self._trend_allows(row, side) else 0.0
        components["macd_confirmation"] = self._macd_score(candles, index, side)
        components["volume_spike"] = 1.0 if self._volume_spike(row) else 0.0

        reason = (
            f"{side} mean reversion: RSI {float(row['rsi']):.1f}, "
            f"deviation {float(row['mean_deviation_pct']) * 100:.2f}%, "
            f"EMA50/EMA200 trend aligned, reversal candle confirmed."
        )
        return ScoreResult(total=min(10.0, sum(components.values())), components=components, reason=reason)

    def _true_range(self, candles: pd.DataFrame) -> pd.Series:
        previous_close = candles["close"].shift(1)
        ranges = pd.concat(
            [
                candles["high"] - candles["low"],
                (candles["high"] - previous_close).abs(),
                (candles["low"] - previous_close).abs(),
            ],
            axis=1,
        )
        return ranges.max(axis=1).fillna(candles["high"] - candles["low"]).clip(lower=0.0)

    def _is_ranging_regime(self, row: pd.Series) -> bool:
        return (
            float(row["ema_50_slope_pct"]) <= float(self.config.max_ema_slope_pct)
            and float(row["atr_pct"]) <= float(self.config.max_atr_pct)
        )

    def _is_strong_breakout(self, candles: pd.DataFrame, index: int) -> bool:
        row = candles.iloc[index]
        atr = self._safe_positive(row.get("atr_14"), fallback=float(row["avg_range_5"]))
        close = float(row["close"])
        range_high = row.get("range_high")
        range_low = row.get("range_low")
        if pd.notna(range_high) and close > float(range_high) + atr * float(self.config.strong_breakout_atr):
            return True
        if pd.notna(range_low) and close < float(range_low) - atr * float(self.config.strong_breakout_atr):
            return True
        return False

    def _trend_allows(self, row: pd.Series, side: str) -> bool:
        if side == "BUY":
            return float(row["ema_50"]) > float(row["ema_200"])
        return float(row["ema_50"]) < float(row["ema_200"])

    def _rsi_extreme(self, row: pd.Series, side: str) -> bool:
        if side == "BUY":
            return float(row["rsi"]) < float(self.config.rsi_lower)
        return float(row["rsi"]) > float(self.config.rsi_upper)

    def _mean_deviation_ok(self, row: pd.Series) -> bool:
        return float(row["mean_deviation_pct"]) >= float(self.config.min_mean_deviation_pct)

    def _confirmation_candle(self, candles: pd.DataFrame, index: int, side: str) -> bool:
        row = candles.iloc[index]
        previous = candles.iloc[index - 1]
        if side == "BUY":
            return float(row["close"]) > float(row["open"]) and float(row["close"]) > float(previous["high"])
        return float(row["close"]) < float(row["open"]) and float(row["close"]) < float(previous["low"])

    def _rsi_score(self, row: pd.Series, side: str) -> float:
        rsi = float(row["rsi"])
        if side == "BUY":
            if rsi <= 20:
                return 2.0
            if rsi < float(self.config.rsi_lower):
                return 1.25
            return 0.0
        if rsi >= 80:
            return 2.0
        if rsi > float(self.config.rsi_upper):
            return 1.25
        return 0.0

    def _mean_deviation_score(self, row: pd.Series) -> float:
        deviation = float(row["mean_deviation_pct"])
        if deviation >= float(self.config.min_mean_deviation_pct) * 2:
            return 2.0
        if deviation >= float(self.config.min_mean_deviation_pct):
            return 1.0
        return 0.0

    def _macd_score(self, candles: pd.DataFrame, index: int, side: str) -> float:
        row = candles.iloc[index]
        previous = candles.iloc[index - 1]
        hist = float(row["macd_hist"])
        hist_improving = hist > float(previous["macd_hist"]) if side == "BUY" else hist < float(previous["macd_hist"])
        crosses_signal = float(row["macd"]) > float(row["macd_signal"]) if side == "BUY" else float(row["macd"]) < float(row["macd_signal"])
        if hist_improving and crosses_signal:
            return 2.0
        if hist_improving:
            return 1.0
        return 0.0

    def _volume_spike(self, row: pd.Series) -> bool:
        average = row.get("avg_volume")
        if average is None or pd.isna(average) or float(average) <= 0:
            return False
        return float(row.get("volume") or 0.0) >= float(average) * 1.2

    def _risk_reward_ok(self, row: pd.Series, stop_loss: float, target_price: float) -> bool:
        close = float(row["close"])
        risk = abs(close - float(stop_loss))
        reward = abs(float(target_price) - close)
        return risk > 0 and reward / risk >= float(self.config.min_rr)

    def _safe_positive(self, value: Any, *, fallback: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return float(fallback)
        if pd.isna(parsed) or parsed <= 0:
            return float(fallback)
        return parsed
