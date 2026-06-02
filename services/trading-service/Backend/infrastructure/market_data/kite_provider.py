from Backend.infrastructure.market_data.base import EnvConfiguredProvider


class KiteProvider(EnvConfiguredProvider):
    provider_name = "kite"
    required_env = ("KITE_API_KEY", "KITE_ACCESS_TOKEN")
