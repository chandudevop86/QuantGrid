from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
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


def test_market_data_provider_interface_aliases(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    reset_backend_modules()

    from Backend.domain.market_data.provider import MarketDataProvider

    class FakeProvider(MarketDataProvider):
        provider_name = "fake"

        def get_ltp(self, symbol: str):
            return {"symbol": symbol.upper(), "price": 100}

        def get_candles(self, symbol: str, interval: str, period: str, limit: int):
            return []

        def subscribe_ticks(self, symbols):
            return None

        def normalize_symbol(self, symbol: str):
            return symbol.upper()

        def health_check(self):
            return {"provider": self.provider_name, "healthy": True}

    provider = FakeProvider()
    assert provider.get_latest_price("nifty")["price"] == 100
    assert provider.get_market_status("nifty")["symbol"] == "NIFTY"


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
    assert result["suitability"] == "live"
    assert result["freshness"] == "fresh"
    assert result["latest_fetch_time"] == "2026-05-29T09:16:00+05:30"
    assert "latest_fetch_at" in result


def test_market_provider_status_reports_paper_suitability(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    reset_backend_modules()

    from Backend.presentation.api import market_api

    class FakeService:
        def health(self, symbol: str = "NIFTY", interval: str = "1m"):
            return {
                "provider_name": "yahoo",
                "provider": "yahoo",
                "paper_suitable": True,
                "live_suitable": False,
                "latest_fetch_at": None,
                "fresh": False,
                "stale": True,
            }

    monkeypatch.setattr(market_api, "get_market_data_service", lambda: FakeService())
    result = market_api.get_market_provider_status(_role="viewer")

    assert result["suitability"] == "paper"
    assert result["freshness"] == "stale"


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


def test_option_chain_prefers_dhan_provider(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "client")
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token")
    reset_backend_modules()

    from Backend.presentation.api import market_api

    def fake_dhan_payload(path, body):
        if path == "optionchain/expirylist":
            return {"data": ["2026-06-25"]}
        return {
            "data": {
                "oc": {
                    "23400.000000": {
                        "ce": {"last_price": 101.5, "oi": 1000, "volume": 50},
                        "pe": {"last_price": 88.25, "oi": 900, "volume": 45},
                    }
                }
            }
        }

    monkeypatch.setattr(market_api, "get_price", lambda symbol, _role=None: {"price": 23400})
    monkeypatch.setattr(market_api, "_dhan_option_payload", fake_dhan_payload)
    monkeypatch.setattr(market_api, "_yahoo_option_rows", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Yahoo should not be used")))

    result = market_api.get_option_chain("NIFTY", strikes_each_side=1, _role="viewer")

    assert result["source"] == "dhan-option-chain"
    assert result["warning"] is None
    atm_row = next(row for row in result["rows"] if row["strike"] == 23400)
    assert atm_row["ce"]["ltp"] == 101.5
    assert atm_row["pe"]["oi"] == 900


def test_option_chain_reports_dhan_token_rejected(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    reset_backend_modules()

    from Backend.presentation.api import market_api

    monkeypatch.setattr(market_api, "get_price", lambda symbol, _role=None: {"price": 23400})
    monkeypatch.setattr(
        market_api,
        "_dhan_option_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("Dhan rejected the saved access token. Open Dhan Login and save a fresh token.")),
    )
    monkeypatch.setattr(
        market_api,
        "_yahoo_option_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("HTTP Error 401: Unauthorized")),
    )

    result = market_api.get_option_chain("NIFTY", strikes_each_side=1, _role="viewer")

    assert result["source"] == "derived-from-underlying"
    assert "save a fresh token" in result["warning"]
    assert "HTTP Error 401" not in result["warning"]


def test_option_chain_falls_back_when_price_provider_is_unavailable(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    reset_backend_modules()

    from Backend.presentation.api import market_api

    monkeypatch.setattr(
        market_api,
        "get_price",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("price feed down")),
    )

    result = market_api.get_option_chain("NIFTY", strikes_each_side=1, _role="viewer")

    assert result["source"] == "synthetic-demo-chain"
    assert result["underlying_price"] > 0
    assert result["pcr"] is not None
    assert result["max_pain"] is not None
    assert "price feed down" in result["warning"]


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


def test_live_candle_validation_rejects_sample_fallback():
    from Backend.application.candle_validation import validate_live_candle

    now = datetime(2026, 6, 2, 9, 16, tzinfo=ZoneInfo("Asia/Kolkata"))
    result = validate_live_candle(
        [{"timestamp": "2026-06-02T09:15:00+05:30", "exchange_timezone": "Asia/Kolkata", "close": 100}],
        mode="live",
        source="sample-fallback",
        now=now,
    )

    assert result.valid_for_execution is False
    assert any("paper/demo only" in item for item in result.diagnostics)


def test_live_market_data_service_rejects_demo_provider(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    reset_backend_modules()

    from Backend.application.market_data_service import MarketDataService
    from Backend.domain.market_data.provider import MarketDataProvider, MarketDataProviderError

    class DemoProvider(MarketDataProvider):
        provider_name = "demo-feed"
        live_suitable = False
        paper_suitable = True

        def get_ltp(self, symbol: str):
            return {"symbol": symbol.upper(), "price": 100}

        def get_candles(self, symbol: str, interval: str, period: str, limit: int):
            return []

        def subscribe_ticks(self, symbols):
            return None

        def normalize_symbol(self, symbol: str):
            return symbol.upper()

        def health_check(self):
            return self.status_payload() | {"healthy": True, "configured": True}

    service = MarketDataService(DemoProvider())

    try:
        service.get_ltp("NIFTY", mode="live")
    except MarketDataProviderError as exc:
        assert "demo/paper only" in str(exc)
    else:
        raise AssertionError("live mode must reject demo providers")


def test_live_market_data_service_accepts_fresh_live_provider(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    reset_backend_modules()

    from Backend.application import market_data_service
    from Backend.application.market_data_service import MarketDataService
    from Backend.domain.market_data.provider import MarketDataProvider

    class FreshLiveProvider(MarketDataProvider):
        provider_name = "broker"
        live_suitable = True
        paper_suitable = True

        def get_ltp(self, symbol: str):
            return {
                "symbol": symbol.upper(),
                "price": 100,
                "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
                "exchange_timezone": "Asia/Kolkata",
            }

        def get_candles(self, symbol: str, interval: str, period: str, limit: int):
            return [
                {
                    "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
                    "exchange_timezone": "Asia/Kolkata",
                    "open": 99,
                    "high": 101,
                    "low": 98,
                    "close": 100,
                    "volume": 100,
                }
            ]

        def subscribe_ticks(self, symbols):
            return None

        def normalize_symbol(self, symbol: str):
            return symbol.upper()

        def health_check(self):
            return self.status_payload() | {"healthy": True, "configured": True}

    monkeypatch.setattr(
        market_data_service,
        "validate_live_candle",
        lambda *args, **kwargs: SimpleNamespace(
            valid=True,
            valid_for_analysis=True,
            valid_for_execution=True,
            market_status="LIVE MARKET",
            delay_seconds=0,
            model_dump=lambda: {"valid_for_execution": True},
        ),
    )
    service = MarketDataService(FreshLiveProvider())

    ltp = service.get_ltp("NIFTY", mode="live")
    candles = service.get_candles("NIFTY", "1m", mode="live")

    assert ltp["price"] == 100
    assert candles["source"] == "live"
    assert candles["fresh"] is True
