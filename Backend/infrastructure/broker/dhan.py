import requests
from typing import List, Dict, Any
from Backend.infrastructure.broker.base import MarketDataAdapter

class DhanAdapter(MarketDataAdapter):

    def __init__(self, client_id: str, access_token: str):
        self.client_id = client_id
        self.access_token = access_token
        self.base_url = "https://api.dhan.co/v2"

    def get_ohlcv(self, symbol: str, interval: str, limit: int):

        headers = {
            "access-token": self.access_token,
            "client-id": self.client_id
        }

        payload = {
            "securityId": symbol,
            "exchangeSegment": "NSE_EQ",
            "instrument": "EQUITY",
            "interval": interval,
            "oi": False
        }

        res = requests.post(
            f"{self.base_url}/charts/historical",
            headers=headers,
            json=payload
        )

        candles = res.json()["data"]["candles"]

        return [
            {
                "timestamp": c[0],
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
            }
            for c in candles
        ]