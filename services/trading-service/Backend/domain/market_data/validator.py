from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    errors: list[str]


class MarketDataValidator:
    # Default minimum candles if caller doesn't specify
    MIN_CANDLES = 30

    @classmethod
    def validate(
        cls,
        candles: pd.DataFrame,
        min_candles: int | None = None,
    ) -> ValidationResult:
        """
        Validate market data before strategy execution.

        Args:
            candles: OHLCV DataFrame
            min_candles: Override default minimum candle requirement

        Returns:
            ValidationResult
        """
        required_candles = min_candles or cls.MIN_CANDLES

        errors: list[str] = []

        # Empty dataframe
        if candles.empty:
            errors.append("No candle data")
            return ValidationResult(valid=False, errors=errors)

        # Required columns
        required = {
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        }

        missing = required - set(candles.columns)

        if missing:
            errors.append(f"Missing columns: {sorted(missing)}")

        # Candle count validation
        if len(candles) < required_candles:
            errors.append(
                f"Only {len(candles)} candles. Need at least {required_candles}"
            )

        # Timestamp validation
        if "timestamp" in candles.columns:
            if candles["timestamp"].duplicated().any():
                errors.append("Duplicate timestamps")

            if not candles["timestamp"].is_monotonic_increasing:
                errors.append("Timestamps not sorted")

        # OHLC validation
        if {"high", "low"}.issubset(candles.columns):
            if (candles["high"] < candles["low"]).any():
                errors.append("High < Low")

        required_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        missing_required = [
            col for col in required_columns
            if col not in candles.columns
        ]

        if missing_required:
            errors.append(
                f"Missing required columns: {missing_required}"
            )
        else:
            ohlcv = candles[required_columns]

            if ohlcv.isna().any().any():
                errors.append("OHLCV contains NaN values")

            if (ohlcv <= 0).any().any():
                errors.append("OHLCV contains invalid values")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
        )