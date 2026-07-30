from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from Backend.core.database import get_db


def load_nifty_candles(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Load NIFTY candles from PostgreSQL and clean the data.
    """

    db = next(get_db())

    query = text("""
        SELECT
            timestamp,
            open,
            high,
            low,
            close,
            volume
        FROM market_candles
        WHERE
            symbol = 'NIFTY'
            AND interval = '1'
            AND timestamp >= :start
            AND timestamp <= :end
        ORDER BY timestamp ASC
    """)

    result = db.execute(
        query,
        {
            "start": start_date,
            "end": end_date,
        },
    )

    rows = result.fetchall()
    db.close()

    if not rows:
        print("No candles found.")
        return pd.DataFrame(
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

    candles = pd.DataFrame(
        rows,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
    )

    candles["timestamp"] = pd.to_datetime(candles["timestamp"])

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

    candles = candles.sort_values("timestamp")
    candles = candles.drop_duplicates("timestamp")

    before = len(candles)

    invalid = candles[
        (candles["open"] <= 0)
        | (candles["high"] <= 0)
        | (candles["low"] <= 0)
        | (candles["close"] <= 0)
        | (candles["high"] < candles["low"])
        | (candles["high"] < candles["open"])
        | (candles["high"] < candles["close"])
        | (candles["low"] > candles["open"])
        | (candles["low"] > candles["close"])
        | (candles["volume"] < 0)
        | (candles[numeric_cols].isna().any(axis=1))
    ]

    if not invalid.empty:
        print("\n========== INVALID CANDLES ==========")
        print(invalid.head(20))
        print(f"Invalid rows: {len(invalid)}")
        print("=====================================\n")

    candles = candles[
        (candles["open"] > 0)
        & (candles["high"] > 0)
        & (candles["low"] > 0)
        & (candles["close"] > 0)
        & (candles["high"] >= candles["low"])
        & (candles["high"] >= candles["open"])
        & (candles["high"] >= candles["close"])
        & (candles["low"] <= candles["open"])
        & (candles["low"] <= candles["close"])
        & (candles["volume"] >= 0)
    ]

    candles = candles.dropna()

    after = len(candles)

    print("=" * 60)
    print("BACKTEST DATASET")
    print("=" * 60)
    print(f"Loaded rows      : {before}")
    print(f"Valid rows       : {after}")
    print(f"Removed rows     : {before - after}")
    print(f"Date From        : {candles['timestamp'].min()}")
    print(f"Date To          : {candles['timestamp'].max()}")
    print("=" * 60)

    return candles.reset_index(drop=True)