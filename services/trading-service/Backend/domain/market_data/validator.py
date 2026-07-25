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
    def validate(cls, candles: pd.DataFrame) -> ValidationResult:

        errors: list[str] = []

        if candles.empty:
            errors.append("No candle data")

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

        if len(candles) < cls.MIN_CANDLES:
            errors.append(
                f"Only {len(candles)} candles. Need at least {cls.MIN_CANDLES}"
            )

        if "timestamp" in candles.columns:

            if candles["timestamp"].duplicated().any():
                errors.append("Duplicate timestamps")

            if not candles["timestamp"].is_monotonic_increasing:
                errors.append("Timestamps not sorted")

        if {"high", "low"}.issubset(candles.columns):

            if (candles["high"] < candles["low"]).any():
                errors.append("High < Low")

        if candles.isna().any().any():
            errors.append("NaN values present")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
        )