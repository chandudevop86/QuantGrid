from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any

import pandas as pd

from Backend.domain.breakout.detector import BreakoutDetectionEngine
from Backend.domain.breakout.models import BreakoutSetup, Side
from Backend.domain.breakout.risk import BreakoutRiskManager
from Backend.domain.breakout.scoring import BreakoutScoringEngine
from Backend.domain.breakout.trend import BreakoutTrendFilter
from Backend.domain.breakout.validator import BreakoutSignalValidator
from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.domain.strategies.base import BaseStrategy, StrategyConfig, normalize_mode
from Backend.domain.strategies.signal_builder import SignalBuilder


@dataclass(slots=True)
class BreakoutConfig(StrategyConfig):
    lookback: int = 20
    min_score: int = 6
    cooldown_minutes: int = 20
    avoid_open_minutes: int = 5
    min_rr: float = 2.0

    @classmethod
    def for_mode(cls, mode: str) -> "BreakoutConfig":
        normalized = normalize_mode(mode)
        base = cls(mode=normalized)
        if normalized == "Conservative":
            return replace(base, min_score=7, cooldown_minutes=25)
        if normalized == "Aggressive":
            return replace(base, min_score=6, cooldown_minutes=15)
        return base


class BreakoutStrategy(BaseStrategy):
    name = "Breakout"

    def __init__(self, config: BreakoutConfig | None = None) -> None:
        super().__init__(config or BreakoutConfig())
        self.config: BreakoutConfig
        self.detector = BreakoutDetectionEngine(lookback=self.config.lookback)
        self.trend = BreakoutTrendFilter()
        self.scoring = BreakoutScoringEngine()
        self.risk = BreakoutRiskManager()
        self.validator = BreakoutSignalValidator(min_score=self.config.min_score, avoid_open_minutes=self.config.avoid_open_minutes)
        self.signal_builder = SignalBuilder()

    def prepare_data(self, data: Any) -> pd.DataFrame:
        candles = super().prepare_data(data)
        if candles.empty:
            return candles
        lookback = int(self.config.lookback)
        out = candles.copy()
        out["breakout_high"] = out["high"].shift(1).rolling(lookback, min_periods=lookback).max()
        out["breakout_low"] = out["low"].shift(1).rolling(lookback, min_periods=lookback).min()
        return out

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        signals: list[StrategySignal] = []
        traded_direction_by_session: set[tuple[str, Side]] = set()
        last_trade_time: pd.Timestamp | None = None

        for index in range(int(self.config.lookback), len(candles)):
            row = candles.iloc[index]
            timestamp = pd.Timestamp(row["timestamp"])
            session = str(row["session_day"])
            if not self.validator.session_open_allowed(candles, index):
                continue
            if last_trade_time is not None and timestamp - last_trade_time < timedelta(minutes=int(self.config.cooldown_minutes)):
                continue

            side = self.trend.allowed_side(row)
            if side is None or (session, side) in traded_direction_by_session:
                continue

            setup = self.detector.detect(candles, index, side)
            trend_aligned = self.trend.aligned(row, side)
            if setup is None:
                continue
            score = self.scoring.score(row, setup, trend_aligned=trend_aligned)
            valid, _ = self.validator.valid_signal(score=score.total, setup=setup, trend_aligned=trend_aligned)
            if not valid:
                continue

            stop_loss, target_price = self.risk.levels(
                row,
                setup,
                min_rr=max(float(context.rr_ratio), float(self.config.min_rr)),
            )
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
                metadata=self._metadata(setup, score.to_dict()),
            )
            if signal is None:
                continue
            signals.append(signal)
            traded_direction_by_session.add((session, side))
            last_trade_time = timestamp

        return signals

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        typed_side: Side = "BUY" if side.upper() == "BUY" else "SELL"
        setup = self.detector.detect(candles, index, typed_side)
        if setup is None:
            row = candles.iloc[index]
            close = float(row["close"])
            atr = max(float(row.get("atr_14", row.get("avg_range_5", 0.0)) or 0.0), 0.05)
            if typed_side == "BUY":
                return close - atr, close + atr * max(2.0, float(context.rr_ratio))
            return close + atr, close - atr * max(2.0, float(context.rr_ratio))
        return self.risk.levels(
            candles.iloc[index],
            setup,
            min_rr=max(float(context.rr_ratio), float(self.config.min_rr)),
        )

    @staticmethod
    def _metadata(setup: BreakoutSetup, score_breakdown: dict[str, Any]) -> dict[str, Any]:
        return {
            "breakout_type": "range_high" if setup.side == "BUY" else "range_low",
            "range_high": round(setup.breakout_range.high, 4),
            "range_low": round(setup.breakout_range.low, 4),
            "range_size": round(setup.breakout_range.size, 4),
            "breakout_distance": round(setup.breakout_distance, 4),
            "score_breakdown": score_breakdown,
            "reason": "; ".join(str(item) for item in score_breakdown["reasons"]),
            "market_signal": f"{setup.side} close-confirmed {setup.reason}",
        }


def run_breakout_strategy(
    data: Any,
    symbol: str,
    capital: float,
    risk_pct: float,
    rr_ratio: float = 2.0,
    config: BreakoutConfig | None = None,
) -> list[StrategySignal]:
    return BreakoutStrategy(config).run(
        data,
        StrategyContext(symbol=symbol, capital=capital, risk_pct=risk_pct, rr_ratio=rr_ratio),
    )
