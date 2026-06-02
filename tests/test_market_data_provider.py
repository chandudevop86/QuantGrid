from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


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


def test_market_data_service_selects_all_supported_providers(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    reset_backend_modules()

    from Backend.application.market_data_service import select_market_data_provider

    assert select_market_data_provider("yahoo").provider_name == "yahoo"
    assert select_market_data_provider("kite").provider_name == "kite"
    assert select_market_data_provider("upstox").provider_name == "upstox"
    assert select_market_data_provider("dhan").provider_name == "dhan"
    assert select_market_data_provider("fyers").provider_name == "fyers"
    assert select_market_data_provider("angel").provider_name == "angel"


def test_nse_market_data_provider_placeholder(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_PROVIDER", "nse")
    reset_backend_modules()

    from Backend.infrastructure.data.market_data_provider import FutureNseMarketDataProvider, get_market_data_provider

    provider = get_market_data_provider()
    assert isinstance(provider, FutureNseMarketDataProvider)
    assert provider.live_suitable is True


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


def test_live_config_supports_requested_yahoo_env_alias(monkeypatch):
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
    monkeypatch.setenv("QUANTGRID_ALLOW_YAHOO_LIVE", "true")
    reset_backend_modules()

    from Backend.core.config import get_settings

    assert get_settings().allow_yahoo_for_live is True


def test_market_provider_status_endpoint_reports_provider(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_PROVIDER", "yahoo")
    reset_backend_modules()

    from Backend.presentation.api import market_api

    class FakeService:
        def health(self, symbol: str = "NIFTY", interval: str = "1m"):
            return {
                "provider_name": "fake-nse",
                "provider": "fake-nse",
                "paper_suitable": True,
                "live_suitable": True,
                "latest_fetch_at": "2026-05-29T09:16:00+05:30",
                "fresh": True,
                "stale": False,
            }

    monkeypatch.setattr(market_api, "get_market_data_service", lambda: FakeService())
    result = market_api.get_market_provider_status(_role="viewer")

    assert result["provider_name"] == "fake-nse"
    assert result["paper_suitable"] is True
    assert "latest_fetch_at" in result


def test_provider_health_failure_reports_feed_down(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_PROVIDER", "kite")
    reset_backend_modules()

    from Backend.application.market_data_service import get_market_data_service

    health = get_market_data_service().health("NIFTY")

    assert health["feed_status"] == "FEED DOWN"
    assert health["fresh"] is False
    assert health["errors"]


def test_market_data_service_memory_cache_fresh_and_stale(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("QUANTGRID_MARKET_CACHE_TTL_SECONDS", "1")
    reset_backend_modules()

    from Backend.application.market_data_service import MarketDataService
    from Backend.domain.market_data.provider import MarketDataProvider

    class FakeProvider(MarketDataProvider):
        provider_name = "fake-live"
        live_suitable = True
        calls = 0

        def get_ltp(self, symbol: str):
            self.calls += 1
            return {
                "symbol": symbol,
                "ltp": 100,
                "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
                "exchange_timezone": "Asia/Kolkata",
            }

        def get_candles(self, symbol: str, interval: str, period: str, limit: int):
            return []

        def subscribe_ticks(self, symbols):
            return None

        def normalize_symbol(self, symbol: str):
            return symbol.upper()

        def health_check(self):
            return self.status_payload() | {"configured": True, "healthy": True}

    provider = FakeProvider()
    service = MarketDataService(provider)
    first = service.get_ltp("NIFTY")
    second = service.get_ltp("NIFTY")

    assert first["cache_status"] == "fresh"
    assert second["cache_status"] == "fresh"
    assert provider.calls == 1


def test_live_candle_validation_rejects_non_ist_timezone(monkeypatch):
    from Backend.application.candle_validation import validate_live_candle

    now = datetime(2026, 6, 2, 9, 16, tzinfo=ZoneInfo("Asia/Kolkata"))
    result = validate_live_candle(
        [{"timestamp": "2026-06-02T09:15:00+05:30", "exchange_timezone": "UTC", "close": 100}],
        mode="live",
        source="broker",
        now=now,
    )

    assert result.valid_for_execution is False
    assert any("Asia/Kolkata" in item for item in result.diagnostics)


def test_live_candle_validation_rejects_zero_price():
    from Backend.application.candle_validation import validate_live_candle

    now = datetime(2026, 6, 2, 9, 16, tzinfo=ZoneInfo("Asia/Kolkata"))
    result = validate_live_candle(
        [{"timestamp": "2026-06-02T09:15:00+05:30", "exchange_timezone": "Asia/Kolkata", "close": 0}],
        mode="live",
        source="broker",
        now=now,
    )

    assert result.valid_for_execution is False
    assert any("greater than zero" in item for item in result.diagnostics)


def test_live_candle_validation_rejects_missing_candles():
    from Backend.application.candle_validation import validate_live_candle

    now = datetime(2026, 6, 2, 9, 20, tzinfo=ZoneInfo("Asia/Kolkata"))
    result = validate_live_candle(
        [{"timestamp": "2026-06-02T09:15:00+05:30", "exchange_timezone": "Asia/Kolkata", "close": 100}],
        mode="live",
        source="broker",
        now=now,
    )

    assert result.valid_for_execution is False
    assert result.missing_candles > 2
    assert any("Missing candle count" in item for item in result.diagnostics)
