from __future__ import annotations


def test_yahoo_market_data_provider_selected(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_PROVIDER", "yahoo")
    reset_backend_modules()

    from Backend.infrastructure.data.market_data_provider import YahooMarketDataProvider, get_market_data_provider

    provider = get_market_data_provider()
    assert isinstance(provider, YahooMarketDataProvider)
    assert provider.warning


def test_broker_market_data_provider_placeholder(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_PROVIDER", "broker")
    reset_backend_modules()

    from Backend.infrastructure.data.market_data_provider import FutureBrokerMarketDataProvider, get_market_data_provider

    assert isinstance(get_market_data_provider(), FutureBrokerMarketDataProvider)
