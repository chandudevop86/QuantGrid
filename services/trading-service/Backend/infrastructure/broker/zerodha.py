import requests
from typing import List, Dict, Any
from Backend.infrastructure.broker.base import MarketDataAdapter

class ZerodhaAdapter(MarketDataAdapter):

    def __init__(self, api_key: str, access_token: str):
        self.api_key = api_key
        self.access_token = access_token
        self.base_url = "https://api.kite.trade"

    def get_ohlcv(self, symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:

        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {self.api_key}:{self.access_token}"
        }

        params = {
            "instrument_token": symbol,
            "interval": interval,
            "limit": limit
        }

        res = requests.get(
            f"{self.base_url}/instruments/historical",
            headers=headers,
            params=params
        )

        data = res.json()["data"]["candles"]

        return [
            {
                "timestamp": c[0],
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
            }
            for c in data
        ]