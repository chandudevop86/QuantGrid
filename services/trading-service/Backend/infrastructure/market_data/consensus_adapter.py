from datetime import datetime, timezone


class ConsensusProviderAdapter:

    def __init__(self, provider):
        self.provider = provider
        self.name = provider.provider_name


    def get_quote(self, symbol: str):

        payload = self.provider.get_ltp(symbol)

        return {
            "ltp": payload.get("ltp"),

            "bid": payload.get("bid"),

            "ask": payload.get("ask"),

            "volume": payload.get("volume"),

            "timestamp": (
                payload.get("timestamp")
                or datetime.now(timezone.utc)
            ),

            "feed_delay_seconds": (
                payload.get("feed_delay_seconds")
                or 0
            ),
        }