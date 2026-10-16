from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import text

from Backend.core.database import SessionLocal


def load_nifty_candles(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Load NIFTY 1m candles for inclusive IST calendar dates, then validate OHLC.

    Accept the worker\'s `1m` interval and the legacy `1` notation. Date bounds
    are 09:15-independent IST calendar days, converted to UTC for storage queries.
    """
    first = date.fromisoformat(start_date)
    last = date.fromisoformat(end_date)
    if last < first:
        raise ValueError("end_date must not precede start_date")
    ist = ZoneInfo("Asia/Kolkata")
    start_utc = datetime.combine(first, time.min, tzinfo=ist).astimezone(timezone.utc)
    end_utc = datetime.combine(last + timedelta(days=1), time.min, tzinfo=ist).astimezone(timezone.utc)

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
            AND interval IN ('1m', '1')
            AND timestamp >= :start
            AND timestamp < :end_exclusive
        ORDER BY timestamp ASC,
                 CASE WHEN interval = '1m' THEN 0 ELSE 1 END
    """)

    with SessionLocal() as db:
        rows = db.execute(query, {
            "start": start_utc,
            "end_exclusive": end_utc,
        }).fetchall()

    if not rows:
        print("No NIFTY 1m candles found for the requested IST dates.")
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

    candles["timestamp"] = pd.to_datetime(candles["timestamp"], utc=True)

    numeric_cols = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    for col in numeric_cols:
        candles[col] = pd.to_numeric(candles[col], errors="coerce")
    # Cash index feeds may not supply traded volume; 0 is not a real
    # volume measurement and must not be used as confirmation of activity.
    candles["volume"] = candles["volume"].fillna(0.0)

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