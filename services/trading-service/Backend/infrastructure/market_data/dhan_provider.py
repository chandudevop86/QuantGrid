from Backend.infrastructure.market_data.base import EnvConfiguredProvider


class DhanProvider(EnvConfiguredProvider):
    provider_name = "dhan"
    required_env = ("QUANTGRID_BROKER_CLIENT_ID", "QUANTGRID_BROKER_ACCESS_TOKEN")
