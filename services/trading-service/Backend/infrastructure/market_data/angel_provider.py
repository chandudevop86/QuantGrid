from Backend.infrastructure.market_data.base import EnvConfiguredProvider


class AngelProvider(EnvConfiguredProvider):
    provider_name = "angel"
    required_env = ("ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_ACCESS_TOKEN")
