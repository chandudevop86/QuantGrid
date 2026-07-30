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
            return ValidationResult(
                valid=False,
                errors=[f"Missing columns: {sorted(missing)}"],
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

        price_cols = ["open", "high", "low", "close"]

        # Check invalid prices
        if (candles[price_cols] <= 0).any().any():
            errors.append("OHLC contains invalid price values")

        # Allow zero volume; only reject negative volume
        if (candles["volume"] < 0).any():
            errors.append("Volume contains negative values")

        # Check NaN
        if candles[price_cols + ["volume"]].isna().any().any():
            errors.append("OHLCV contains NaN values")

        # ---------- DEBUG ----------
        bad = candles[
            (candles["open"] <= 0)
            | (candles["high"] <= 0)
            | (candles["low"] <= 0)
            | (candles["close"] <= 0)
            | (candles["volume"] < 0)
        ]

        if not bad.empty:
            print("\n========== INVALID CANDLES ==========")
            print(bad.head(20))
            print(f"Total bad rows: {len(bad)}")
            print("=====================================\n")
        # ---------------------------

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
        )