from Backend.infrastructure.market_data.base import EnvConfiguredProvider


class UpstoxProvider(EnvConfiguredProvider):
    provider_name = "upstox"
    required_env = ("UPSTOX_ACCESS_TOKEN",)
