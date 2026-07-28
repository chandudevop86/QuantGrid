from __future__ import annotations
from urllib import response

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
            to_date = today.strftime("%Y-%m-%d")

            if latest_timestamp:
                if hasattr(latest_timestamp, "strftime"):
                    from_date = latest_timestamp.strftime("%Y-%m-%d")
                else:
                    from_date = str(latest_timestamp)[:10]
            else:
                from_date = (
                    today - timedelta(days=5)
                ).strftime("%Y-%m-%d")

            print("latest_timestamp:", latest_timestamp)
            print("from_date:", from_date)
            print("to_date:", to_date)
            response = self.client.intraday_minute_data(

                security_id=security_id,

                exchange_segment=exchange_segment,

                instrument_type="INDEX",

                interval=interval,

                from_date=from_date,

                to_date=to_date

            )
            from pprint import pprint

            print("FULL RESPONSE")
            pprint(response)
            print("status:", response.get("status"))
            print("remarks:", response.get("remarks"))
            print("data length:", len(response.get("data", [])))

            if not response:

                return pd.DataFrame()

            data = response.get("data", {})

            print(type(response.get("data")))
            pprint(response.get("data"))


            if not data:

                return pd.DataFrame()



            df = pd.DataFrame(data)
            print("Before conversion:")
            print(df)


            if df.empty:

                return df



            # Dhan timestamp is UTC epoch seconds
            # Convert to IST

            df["timestamp"] = pd.to_datetime(

                df["timestamp"],

                unit="s",

                utc=True

            )
            print("After UTC conversion:")
            print(df["timestamp"])


            df["timestamp"] = (

                df["timestamp"]

                .dt.tz_convert("Asia/Kolkata")

                .dt.tz_localize(None)

            )
            
            print("After IST conversion:")
            print(df["timestamp"])
        # NSE cash market session filter
            market_start = "09:15:00"
            market_end = "15:30:00"


            df = df[
                df["timestamp"].dt.strftime("%H:%M:%S").between(
                    market_start,
                    market_end
                )
            ]
            print("After market filter:")
            print(df)

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