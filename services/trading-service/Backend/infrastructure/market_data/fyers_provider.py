from Backend.infrastructure.market_data.base import EnvConfiguredProvider


class FyersProvider(EnvConfiguredProvider):
    provider_name = "fyers"
    required_env = ("FYERS_CLIENT_ID", "FYERS_ACCESS_TOKEN")
