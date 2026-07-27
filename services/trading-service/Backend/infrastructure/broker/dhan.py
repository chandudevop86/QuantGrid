import requests
from typing import List, Dict, Any

from Backend.infrastructure.broker.base import MarketDataAdapter


class DhanAdapter(MarketDataAdapter):

    timeout_seconds = 10

    def __init__(
        self,
        client_id: str,
        access_token: str
    ):
        self.client_id = client_id
        self.access_token = access_token
        self.base_url = "https://api.dhan.co/v2"


    def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        limit: int
    ) -> Dict[str, Any]:

        headers = {
            "access-token": self.access_token,
            "client-id": self.client_id,
            "Content-Type": "application/json",
        }


        payload = {
            "securityId": symbol,
            "exchangeSegment": "NSE_EQ",
            "instrument": "EQUITY",
            "interval": interval,
            "oi": False,
        }


        response = requests.post(
            f"{self.base_url}/charts/historical",
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )


        response.raise_for_status()


        body = response.json()


        candles = (
            body
            .get("data", {})
            .get("candles", [])
        )


        normalized = normalize_candles(
            candles[:limit]
        )


        return {
            "symbol": symbol,
            "interval": interval,
            "candles": normalized,
            "source": "dhan",
        }



def normalize_candles(
    candles: List[list]
) -> List[dict]:
    """
    Normalize Dhan candle response.

    Removes duplicate timestamps
    Sorts ascending
    Converts array format to dict
    """

    seen = set()

    cleaned = []


    for candle in candles:

        if len(candle) < 6:
            continue


        timestamp = candle[0]


        if timestamp in seen:
            continue


        seen.add(timestamp)


        cleaned.append(
            {
                "timestamp": timestamp,
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": int(candle[5]),
            }
        )


    cleaned.sort(
        key=lambda x: x["timestamp"]
    )


    return cleaned