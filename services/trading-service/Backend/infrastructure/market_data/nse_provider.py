from Backend.infrastructure.market_data.base import EnvConfiguredProvider


class NseLicensedProvider(EnvConfiguredProvider):
    """Fail-closed placeholder for a licensed NSE market-data adapter.

    Do not implement this by scraping nseindia.com. Wire an approved/licensed NSE
    feed (or authorized vendor) behind the normal MarketDataProvider contract.
    """

    provider_name = "nse"
    live_suitable = True
    paper_suitable = True
    required_env = ("NSE_DATA_LICENSE_ID",)
    warning = "Licensed NSE adapter is not connected yet; website scraping is not supported."
