from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd

from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.models.context import StrategyContext
from Backend.domain.models.signal import StrategySignal
from Backend.domain.market_data.validator import MarketDataValidator
import logging

logger = logging.getLogger(__name__)

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

    def run(
    self,
    data: Any,
    context: StrategyContext
    ) -> list[StrategySignal]:

        # Explicit backtest-only prepared-data path.
        # Normal and live strategy execution retain their existing behavior.
        from Backend.domain.strategies.backtest_cache_context import (
            backtest_cache_allowed,
        )

        prepared = context.params.get("_backtest_prepared_frame")
        if prepared is not None and backtest_cache_allowed():
            if self.__class__.__name__ != "BreakoutStrategy":
                raise ValueError(
                    "Prepared backtest cache is restricted to BreakoutStrategy"
                )
            if not isinstance(prepared, pd.DataFrame):
                raise TypeError("Backtest prepared frame must be a DataFrame")

            raw = pd.DataFrame(data)
            required = {"timestamp", "open", "high", "low", "close", "volume"}

            if not required.issubset(raw.columns):
                raise ValueError("Backtest cache input is missing OHLCV fields")
            if not required.issubset(prepared.columns):
                raise ValueError("Backtest cache is missing OHLCV fields")
            if len(raw) != len(prepared):
                raise ValueError("Backtest cache candle count mismatch")

            from Backend.domain.indicators.indicators import prepare_ohlcv

            normalized = prepare_ohlcv(raw)

            if len(normalized) != len(prepared):
                raise ValueError("Backtest cache normalization mismatch")

            from pandas.testing import assert_frame_equal

            try:
                assert_frame_equal(
                    normalized[list(sorted(required))].reset_index(drop=True),
                    prepared[list(sorted(required))].reset_index(drop=True),
                    check_dtype=False,
                    check_exact=False,
                    rtol=1e-10,
                    atol=1e-10,
                )
            except AssertionError as exc:
                raise ValueError(
                    "Backtest cache does not match current candles"
                ) from exc

            candles = prepared.copy()
        else:
            candles = self.prepare_data(data)

        logger.debug(
            "Prepared candles: rows=%s columns=%s",
            len(candles),
            list(candles.columns)
        )

        if candles.empty:
            logger.warning("Empty candle dataframe received")
            return []

        validation = MarketDataValidator.validate(candles)

        if not validation.valid:
            logger.warning(
                "Market data validation failed: %s",
                validation.errors
            )
            return []

        self.validate_inputs(candles, context)

        signals = self.generate_signals(
            candles,
            context
        )

        logger.info(
            "Strategy=%s generated signals=%s",
            self.__class__.__name__,
            len(signals)
        )

        return signals
    def generate_signal(self, candles: pd.DataFrame, context: StrategyContext) -> list[StrategySignal]:
        return self.generate_signals(candles, context)

    def validate_inputs(self, candles: pd.DataFrame, context: StrategyContext) -> None:
        required = {"open", "high", "low", "close"}
        missing = required.difference(set(candles.columns))
        if missing:
            raise ValueError(f"Missing required candle columns: {', '.join(sorted(missing))}")
        if not context.symbol:
            raise ValueError("Strategy context requires a symbol")

    def explain_signal(self, signal: StrategySignal) -> str:
        reason = signal.metadata.get("reason") or signal.metadata.get("validation_reason")
        if reason:
            return str(reason)
        return f"{signal.strategy_name} generated a {signal.side} signal for {signal.symbol}."

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


def risk_fraction(risk_pct: float) -> float:
    value = float(risk_pct or 0.0)
    return max(0.0, value) / 100.0


def recent_true(series: pd.Series, index: int, lookback: int) -> int | None:
    left = max(0, int(index) - int(lookback))
    window = series.iloc[left : index + 1]
    matches = window[window.fillna(False)]
    if matches.empty:
        return None
    return int(matches.index[-1])
