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


def test_live_config_rejects_yahoo_by_default(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "postgresql://quant:secret@localhost/quantgrid")
    monkeypatch.setenv("QUANTGRID_ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("BROKER_LIVE_ENABLED", "true")
    monkeypatch.setenv("QUANTGRID_BROKER_PROVIDER", "dhan")
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "client")
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token")
    monkeypatch.setenv("QUANTGRID_CAPITAL", "100000")
    monkeypatch.setenv("QUANTGRID_RISK_PER_TRADE_PCT", "1")
    monkeypatch.setenv("QUANTGRID_MAX_DAILY_LOSS", "3000")
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_PROVIDER", "yahoo")
    reset_backend_modules()

    from Backend.core.config import validate_security_config

    try:
        validate_security_config()
    except RuntimeError as exc:
        assert "Yahoo is paper/demo only" in str(exc)
    else:
        raise AssertionError("live trading must reject Yahoo unless explicitly allowed")


def test_market_provider_status_endpoint_reports_provider(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_PROVIDER", "yahoo")
    reset_backend_modules()

    from Backend.infrastructure.data import market_data_provider
    from Backend.presentation.api import market_api

    class FakeProvider(market_data_provider.MarketDataProvider):
        provider_name = "fake-nse"
        live_suitable = True
        paper_suitable = True

        def fetch_chart(self, symbol: str, *, interval: str = "1m", period: str = "1d"):
            return {}

        def get_latest_price(self, symbol: str):
            return {"symbol": symbol, "price": 100, "source": self.provider_name}

        def get_candles(self, symbol: str, interval: str, limit: int):
            self.latest_fetch_at = "2026-05-29T09:16:00+05:30"
            return [
                {
                    "timestamp": "2026-05-29T09:15:00+05:30",
                    "exchange_timezone": "Asia/Kolkata",
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                }
            ]

        def get_market_status(self, symbol: str):
            return self.status_payload()

    monkeypatch.setattr(market_api, "get_market_data_provider", lambda: FakeProvider())
    result = market_api.get_market_provider_status(_role="viewer")

    assert result["provider_name"] == "fake-nse"
    assert result["paper_suitable"] is True
    assert "latest_fetch_at" in result
