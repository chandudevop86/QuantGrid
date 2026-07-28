from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    errors: list[str]


class MarketDataValidator:
    MIN_CANDLES = 30

    @classmethod
    def validate(
        cls,
        candles: pd.DataFrame,
        min_candles: int | None = None,
    ) -> ValidationResult:
        """
        Validate market data before strategy execution.
        """
        required_candles = min_candles or cls.MIN_CANDLES
        errors: list[str] = []

        if candles.empty:
            return ValidationResult(
                valid=False,
                errors=["No candle data"],
            )

        required_columns = {
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        }

        missing = required_columns - set(candles.columns)
        if missing:
            errors.append(f"Missing columns: {sorted(missing)}")
            return ValidationResult(
                valid=False,
                errors=errors,
            )

        if len(candles) < required_candles:
            errors.append(
                f"Only {len(candles)} candles. Need at least {required_candles}"
            )

        if candles["timestamp"].duplicated().any():
            errors.append("Duplicate timestamps")

        if not candles["timestamp"].is_monotonic_increasing:
            errors.append("Timestamps not sorted")

        if (candles["high"] < candles["low"]).any():
            errors.append("High < Low")

        ohlcv = candles[
            ["open", "high", "low", "close", "volume"]
        ]

        if ohlcv.isna().any().any():
            errors.append("OHLCV contains NaN values")

        if (ohlcv <= 0).any().any():
            errors.append("OHLCV contains invalid values")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
        )