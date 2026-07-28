from __future__ import annotations

import pandas as pd

from dhanhq import DhanContext, dhanhq

from app.config import settings
from datetime import date, timedelta

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
                settings.DHAN_ACCESS_TOKEN
            )


            self.client = dhanhq(
                self.context
            )



    def connected(self) -> bool:

        return self.client is not None



    def get_connection_status(self):

        return {

            "provider": "dhan",

            "connected": self.connected()

        }



    def get_intraday_candles(
    self,
    security_id: str,
    exchange_segment: str,
    interval: str = "1",
    latest_timestamp : str | None = None
    ):

        if not self.client:

            raise Exception(
                "Dhan credentials missing"
            )


        try:

            today = date.today()
            if latest_timestamp:
                from_date = latest_timestamp[:10]
            else:
                from_date = (
                    today - timedelta(days=5)
                ).strftime("%Y-%m-%d")


                to_date = today.strftime(
                    "%Y-%m-%d"
                )


            response = self.client.intraday_minute_data(

                security_id=security_id,

                exchange_segment=exchange_segment,

                instrument_type="INDEX",

                interval=interval,

                from_date=from_date,

                to_date=to_date

            )


            if not response:

                return pd.DataFrame()



            data = response.get(
                "data",
                {}
            )


            if not data:

                return pd.DataFrame()



            df = pd.DataFrame(data)


            if df.empty:

                return df



            # Dhan timestamp is UTC epoch seconds
            # Convert to IST

            df["timestamp"] = pd.to_datetime(

                df["timestamp"],

                unit="s",

                utc=True

            )


            df["timestamp"] = (

                df["timestamp"]

                .dt.tz_convert("Asia/Kolkata")

                .dt.tz_localize(None)

            )
        # NSE cash market session filter
            market_start = "09:15:00"
            market_end = "15:30:00"


            df = df[
                df["timestamp"].dt.strftime("%H:%M:%S").between(
                    market_start,
                    market_end
                )
            ]

            return df[
                [
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume"
                ]
            ]



        except Exception as e:

            raise Exception(
                f"Dhan intraday failed: {e}"
            )