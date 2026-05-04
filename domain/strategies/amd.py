from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, NamedTuple

import pandas as pd

from app.domain.models.context import StrategyContext
from app.domain.models.signal import StrategySignal
from app.domain.strategies.base import BaseStrategy, StrategyConfig, normalize_mode, recent_true
from app.domain.strategies.scoring import ScoringEngine
from app.domain.strategies.signal_builder import SignalBuilder


@dataclass(slots=True)
class ConfluenceConfig(StrategyConfig):
    accumulation_lookback: int = 10
    manipulation_lookback: int = 6
    min_fvg_size: float = 0.35
    retest_tolerance_pct: float = 0.0015
    max_retest_bars: int = 6
    min_score_conservative: float = 7.4
    min_score_balanced: float = 6.2
    min_score_aggressive: float = 4.8
    require_vwap_alignment: bool = True
    require_trend_alignment: bool = True
    require_liquidity_sweep: bool = True
    require_fvg_confirmation: bool = True
    require_distribution_phase: bool = True

    @classmethod
    def for_mode(cls, mode: str) -> "ConfluenceConfig":
        normalized = normalize_mode(mode)
        base = cls(mode=normalized)
        if normalized == "Conservative":
            return replace(base, accumulation_lookback=12, manipulation_lookback=7, min_fvg_size=0.45, max_retest_bars=4, duplicate_signal_cooldown_bars=14)
        if normalized == "Aggressive":
            return replace(base, accumulation_lookback=8, manipulation_lookback=4, min_fvg_size=0.25, max_retest_bars=8, require_distribution_phase=False, duplicate_signal_cooldown_bars=8)
        return base


class _Alignments(NamedTuple):
    trend_ok: bool
    vwap_ok: bool
    momentum_ok: bool


class _Levels(NamedTuple):
    stop_loss: float
    target_price: float


class AMDStrategy(BaseStrategy):
    name = "AMD + FVG + Supply/Demand"

    def __init__(self, config: ConfluenceConfig | None = None) -> None:
        super().__init__(config or ConfluenceConfig())
        self.config: ConfluenceConfig
        self.scoring = ScoringEngine()
        self.signal_builder = SignalBuilder()

    def prepare_data(self, data: Any) -> pd.DataFrame:
        candles = super().prepare_data(data)
        if candles.empty:
            return candles
        out = candles.copy()
        out["bullish_manipulation"] = (out["low"] < out["recent_low"]) & (out["close"] > out["recent_low"])
        out["bearish_manipulation"] = (out["high"] > out["recent_high"]) & (out["close"] < out["recent_high"])
        out["bullish_distribution"] = (out["close"] > out["recent_high"]) & (out["close"] > out["ema_fast"])
        out["bearish_distribution"] = (out["close"] < out["recent_low"]) & (out["close"] < out["ema_fast"])
        out["bullish_fvg"] = out["bullish_fvg_gap"] >= float(self.config.min_fvg_size)
        out["bearish_fvg"] = out["bearish_fvg_gap"] >= float(self.config.min_fvg_size)
        return out

    def generate_signals(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        threshold = self.scoring.threshold(self.config.mode, conservative=self.config.min_score_conservative, balanced=self.config.min_score_balanced, aggressive=self.config.min_score_aggressive)
        trades: list[StrategySignal] = []
        trade_counts: dict[str, int] = {}
        last_signal_index = {"BUY": -10_000, "SELL": -10_000}
        start_index = max(5, int(self.config.accumulation_lookback), int(self.config.manipulation_lookback))
        for index in range(start_index, len(candles)):
            row = candles.iloc[index]
            day_key = str(row["session_day"])
            if trade_counts.get(day_key, 0) >= max(1, int(self.config.max_trades_per_day)):
                continue
            for side in ("BUY", "SELL"):
                if index - last_signal_index[side] < int(self.config.duplicate_signal_cooldown_bars):
                    continue
                signal = self._evaluate_bar(candles, index, side=side, context=context, threshold=threshold)
                if signal is None:
                    continue
                trades.append(signal)
                trade_counts[day_key] = trade_counts.get(day_key, 0) + 1
                last_signal_index[side] = index
                break
        return trades

    def calculate_levels(self, candles: pd.DataFrame, index: int, side: str, context: StrategyContext) -> tuple[float, float]:
        row = candles.iloc[index]
        is_buy = side.upper() == "BUY"
        fvg_col = "bullish_fvg" if is_buy else "bearish_fvg"
        recent_fvg = recent_true(candles[fvg_col], index, int(self.config.max_retest_bars))
        levels = self._compute_levels(row, is_buy=is_buy, recent_fvg=recent_fvg, candles=candles, rr_ratio=context.rr_ratio)
        return levels.stop_loss, levels.target_price

    def _evaluate_bar(self, candles: pd.DataFrame, index: int, *, side: str, context: StrategyContext, threshold: float) -> StrategySignal | None:
        is_buy = side == "BUY"
        row = candles.iloc[index]
        manip_col = "bullish_manipulation" if is_buy else "bearish_manipulation"
        fvg_col = "bullish_fvg" if is_buy else "bearish_fvg"
        recent_manip = recent_true(candles[manip_col], index, int(self.config.max_retest_bars))
        recent_fvg = recent_true(candles[fvg_col], index, int(self.config.max_retest_bars))
        alignments = self._compute_alignments(row, is_buy)
        dist_col = "bullish_distribution" if is_buy else "bearish_distribution"
        if self.config.require_liquidity_sweep and recent_manip is None:
            return None
        if self.config.require_fvg_confirmation and recent_fvg is None:
            return None
        if self.config.require_distribution_phase and not bool(row[dist_col]):
            return None
        if self.config.require_trend_alignment and not alignments.trend_ok:
            return None
        if self.config.require_vwap_alignment and not alignments.vwap_ok:
            return None
        score = self._compute_score(row, is_buy=is_buy, recent_manip=recent_manip, recent_fvg=recent_fvg, alignments=alignments)
        if not self.scoring.passed(score, threshold):
            return None
        levels = self._compute_levels(row, is_buy=is_buy, recent_fvg=recent_fvg, candles=candles, rr_ratio=context.rr_ratio)
        amd_phase = "manipulation" if is_buy else "distribution"
        return self.signal_builder.build(row, strategy_name=self.name, symbol=context.symbol, side=side, capital=context.capital, risk_pct=context.risk_pct, stop_loss=levels.stop_loss, target_price=levels.target_price, score=score, metadata={"zone_type": "demand" if is_buy else "supply", "imbalance_type": "FVG", "amd_phase": amd_phase, "market_signal": f"{side} + FVG + {amd_phase}"})

    def _compute_alignments(self, row: pd.Series, is_buy: bool) -> _Alignments:
        close = float(row["close"])
        e9, e21, e50, e200 = float(row["ema_9"]), float(row["ema_21"]), float(row["ema_50"]), float(row["ema_200"])
        macd, macd_sig, rsi = float(row["macd"]), float(row["macd_signal"]), float(row["rsi"])
        if is_buy:
            return _Alignments(close >= e9 >= e21 >= e50 >= e200, close >= float(row["vwap"]), macd >= macd_sig and rsi >= 50.0)
        return _Alignments(close <= e9 <= e21 <= e50 <= e200, close <= float(row["vwap"]), macd <= macd_sig and rsi <= 50.0)

    def _compute_score(self, row: pd.Series, *, is_buy: bool, recent_manip: int | None, recent_fvg: int | None, alignments: _Alignments) -> float:
        dist_col = "bullish_distribution" if is_buy else "bearish_distribution"
        fvg_gap_col = "bullish_fvg_gap" if is_buy else "bearish_fvg_gap"
        score = 4.0 if recent_manip is not None else 0.0
        score += 3.0 if bool(row[dist_col]) else 0.0
        score += 3.0 if recent_fvg is not None else 0.0
        score += 1.0 if float(row[fvg_gap_col]) >= float(self.config.min_fvg_size) * 1.25 else 0.0
        score += 2.0 if alignments.trend_ok else 0.0
        score += 1.0 if alignments.vwap_ok else 0.0
        score += 1.0 if alignments.momentum_ok else 0.0
        return score

    def _compute_levels(self, row: pd.Series, *, is_buy: bool, recent_fvg: int | None, candles: pd.DataFrame, rr_ratio: float) -> _Levels:
        close = float(row["close"])
        buffer = max(float(row["avg_range_5"]) * 0.2, close * float(self.config.retest_tolerance_pct), 0.05)
        if is_buy:
            anchor = float(candles.iloc[recent_fvg]["high"]) if recent_fvg is not None else float(row["low"])
            stop_loss = min(float(row["low"]), anchor) - buffer
            if stop_loss >= close:
                stop_loss = close - max(buffer, 0.1)
            return _Levels(stop_loss, close + (close - stop_loss) * float(rr_ratio))
        anchor = float(candles.iloc[recent_fvg]["low"]) if recent_fvg is not None else float(row["high"])
        stop_loss = max(float(row["high"]), anchor) + buffer
        if stop_loss <= close:
            stop_loss = close + max(buffer, 0.1)
        return _Levels(stop_loss, close - (stop_loss - close) * float(rr_ratio))
