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

        # --------------------------------------------------
        # Empty DataFrame
        # --------------------------------------------------

        if candles.empty:
            return ValidationResult(
                valid=False,
                errors=["No candle data"],
            )

        # --------------------------------------------------
        # Required columns
        # --------------------------------------------------

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

        # --------------------------------------------------
        # Convert numeric columns
        # --------------------------------------------------

        numeric_cols = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        for col in numeric_cols:
            candles[col] = pd.to_numeric(
                candles[col],
                errors="coerce",
            )

        candles["timestamp"] = pd.to_datetime(
            candles["timestamp"],
            errors="coerce",
        )

        # --------------------------------------------------
        # Debug
        # --------------------------------------------------

        print("\n================ MARKET DATA VALIDATOR ================")
        print(f"Rows : {len(candles)}")
        print("\nData Types:")
        print(candles.dtypes)

        print("\nHead:")
        print(candles.head())

        print("\nTail:")
        print(candles.tail())

        print("\nNaN Counts:")
        print(candles[numeric_cols].isna().sum())

        print("\nStatistics:")
        print(candles[numeric_cols].describe())
        print("=======================================================\n")

        # --------------------------------------------------
        # Candle count
        # --------------------------------------------------

        if len(candles) < required_candles:
            errors.append(
                f"Only {len(candles)} candles. Need at least {required_candles}"
            )

        # --------------------------------------------------
        # Timestamp validation
        # --------------------------------------------------

        if candles["timestamp"].isna().any():
            errors.append("Invalid timestamps")

        if candles["timestamp"].duplicated().any():
            errors.append("Duplicate timestamps")

        if not candles["timestamp"].is_monotonic_increasing:
            errors.append("Timestamps not sorted")

        # --------------------------------------------------
        # NaN validation
        # --------------------------------------------------

        if candles[numeric_cols].isna().any().any():
            errors.append("OHLCV contains NaN values")

        # --------------------------------------------------
        # Invalid prices
        # --------------------------------------------------

        if (candles[["open", "high", "low", "close"]] <= 0).any().any():
            errors.append("OHLC contains invalid price values")

        # Allow zero volume
        if (candles["volume"] < 0).any():
            errors.append("Volume contains negative values")

        # --------------------------------------------------
        # OHLC relationship validation
        # --------------------------------------------------

        if (candles["high"] < candles["low"]).any():
            errors.append("High < Low")

        if (candles["high"] < candles["open"]).any():
            errors.append("High < Open")

        if (candles["high"] < candles["close"]).any():
            errors.append("High < Close")

        if (candles["low"] > candles["open"]).any():
            errors.append("Low > Open")

        if (candles["low"] > candles["close"]).any():
            errors.append("Low > Close")

        # --------------------------------------------------
        # Debug invalid rows
        # --------------------------------------------------

        invalid_rows = candles[
            (candles["open"] <= 0)
            | (candles["high"] <= 0)
            | (candles["low"] <= 0)
            | (candles["close"] <= 0)
            | (candles["volume"] < 0)
            | (candles["open"].isna())
            | (candles["high"].isna())
            | (candles["low"].isna())
            | (candles["close"].isna())
            | (candles["volume"].isna())
        ]

        if not invalid_rows.empty:
            print("\n========== INVALID OHLCV ROWS ==========")
            print(invalid_rows.head(20))
            print(f"Total invalid rows: {len(invalid_rows)}")
            print("========================================\n")

        relationship_errors = candles[
            (candles["high"] < candles["low"])
            | (candles["high"] < candles["open"])
            | (candles["high"] < candles["close"])
            | (candles["low"] > candles["open"])
            | (candles["low"] > candles["close"])
        ]

        if not relationship_errors.empty:
            print("\n========== INVALID OHLC RELATION ==========")
            print(relationship_errors.head(20))
            print(f"Total relation errors: {len(relationship_errors)}")
            print("===========================================\n")

        # --------------------------------------------------
        # Print validation result
        # --------------------------------------------------

        if errors:
            print("\n========== VALIDATION FAILED ==========")
            for err in errors:
                print(f"- {err}")
            print("=======================================\n")
        else:
            print("\n✅ Market data validation PASSED\n")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
        )