from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from dhanhq import DhanContext, dhanhq

from app.config import settings


class DhanProvider:
    def __init__(self):
        self.client = None
        self.context = None

        if (
            settings.DHAN_CLIENT_ID
            and settings.DHAN_ACCESS_TOKEN
        ):
            self.context = DhanContext(
                settings.DHAN_CLIENT_ID,
                settings.DHAN_ACCESS_TOKEN,
            )

            self.client = dhanhq(self.context)

    def connected(self) -> bool:
        return self.client is not None

    def get_connection_status(self):
        return {
            "provider": "dhan",
            "connected": self.connected(),
        }

    def get_intraday_candles(
        self,
        security_id: str,
        exchange_segment: str,
        interval: str = "1",
        latest_timestamp: str | None = None,
    ):
        """
        Download recent intraday candles.
        Returns the last 5 trading days.
        """

        if not self.client:
            raise Exception("Dhan credentials missing")

        try:
            today = date.today()

            from_date = (
                today - timedelta(days=5)
            ).strftime("%Y-%m-%d")

            to_date = today.strftime("%Y-%m-%d")

            print(f"latest_timestamp: {latest_timestamp}")
            print(f"from_date: {from_date}")
            print(f"to_date: {to_date}")

            response = self.client.intraday_minute_data(
                security_id=security_id,
                exchange_segment=exchange_segment,
                instrument_type="INDEX",
                interval=interval,
                from_date=from_date,
                to_date=to_date,
            )

            if not response:
                return pd.DataFrame()

            data = response.get("data", {})

            if not data or not data.get("timestamp"):
                return pd.DataFrame()

            df = pd.DataFrame(data)

            if df.empty:
                return df

            df["timestamp"] = (
                    pd.to_datetime(
                        df["timestamp"],
                        unit="s",
                        utc=True,
                    )
                )

            df = df[
                df["timestamp"]
                .dt.strftime("%H:%M:%S")
                .between("09:15:00", "15:30:00")
            ]

            print("Fetched:", len(df), "candles")

            return df[
                [
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ]
            ]

        except Exception as e:
            raise Exception(f"Dhan intraday failed: {e}")

    def get_intraday_history(
        self,
        security_id: str,
        exchange_segment: str,
        interval: str,
        from_date: date,
        to_date: date,
    ):
        """
        Download historical intraday candles from Dhan.
        Used for initial database backfill.
        """

        if not self.client:
            raise Exception("Dhan credentials missing")

        try:
            response = self.client.intraday_minute_data(
                security_id=security_id,
                exchange_segment=exchange_segment,
                instrument_type="INDEX",
                interval=interval,
                from_date=from_date.strftime("%Y-%m-%d"),
                to_date=to_date.strftime("%Y-%m-%d"),
            )

            if not response:
                return pd.DataFrame()

            data = response.get("data", {})

            if not data or not data.get("timestamp"):
                return pd.DataFrame()

            df = pd.DataFrame(data)

            if df.empty:
                return df

            df["timestamp"] = (
                pd.to_datetime(
                    df["timestamp"],
                    unit="s",
                    utc=True,
                )
                .dt.tz_convert("Asia/Kolkata")
                .dt.tz_localize(None)
            )

            df = df[
                df["timestamp"]
                .dt.strftime("%H:%M:%S")
                .between("09:15:00", "15:30:00")
            ]

            df = (
                df.sort_values("timestamp")
                .drop_duplicates(subset=["timestamp"])
                .reset_index(drop=True)
            )

            numeric_cols = [
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]

            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(
                        df[col],
                        errors="coerce",
                    )

            df = df.dropna(
                subset=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                ]
            )

            if "volume" in df.columns:
                df["volume"] = (
                    df["volume"]
                    .fillna(0)
                    .astype(int)
                )

            print(
                f"Backfill {from_date} -> {to_date}: {len(df)} candles"
            )

            return df[
                [
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ]
            ]

        except Exception as e:
            raise Exception(f"Dhan history failed: {e}")