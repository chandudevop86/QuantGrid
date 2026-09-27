from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


def _provider(name: str, *, price: float | None = None, fail: bool = False):
    from Backend.domain.market_data.provider import MarketDataProvider, MarketDataProviderError

    class FakeProvider(MarketDataProvider):
        provider_name = name
        live_suitable = name != "yahoo"
        paper_suitable = True

        def get_ltp(self, symbol: str):
            if fail:
                raise MarketDataProviderError(f"{name} unavailable")
            return {
                "symbol": symbol.upper(),
                "ltp": price or 100.0,
                "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
                "exchange_timezone": "Asia/Kolkata",
            }

        def get_candles(self, symbol: str, interval: str, period: str, limit: int):
            if fail:
                raise MarketDataProviderError(f"{name} unavailable")
            return [
                {
                    "symbol": symbol.upper(),
                    "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
                    "exchange_timezone": "Asia/Kolkata",
                    "open": 99.0,
                    "high": 101.0,
                    "low": 98.0,
                    "close": price or 100.0,
                    "volume": 1,
                }
            ]

        def subscribe_ticks(self, symbols):
            return None

        def normalize_symbol(self, symbol: str):
            return symbol.upper()

        def health_check(self):
            return self.status_payload() | {
                "configured": True,
                "connected": not fail,
                "healthy": not fail,
            }

    return FakeProvider()


def test_paper_fallback_uses_next_provider_and_reports_source():
    from Backend.infrastructure.market_data.fallback_provider import PaperFallbackProvider

    provider = PaperFallbackProvider([
        _provider("dhan", fail=True),
        _provider("yahoo", price=25000),
    ])

    payload = provider.get_ltp("NIFTY")

    assert payload["ltp"] == 25000
    assert payload["provider"] == "yahoo"
    assert payload["fallback_used"] is True
    assert provider.active_provider_name == "yahoo"
    assert provider.failures == ["dhan: dhan unavailable"]


def test_paper_fallback_fails_closed_when_all_sources_fail():
    from Backend.domain.market_data.provider import MarketDataProviderError
    from Backend.infrastructure.market_data.fallback_provider import PaperFallbackProvider

    provider = PaperFallbackProvider([
        _provider("dhan", fail=True),
        _provider("yahoo", fail=True),
    ])

    with pytest.raises(MarketDataProviderError, match="All paper market data providers failed"):
        provider.get_candles("NIFTY", "1m", "1d", 100)


def test_auto_provider_chain_is_configurable(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_PROVIDER_CHAIN", "dhan,yahoo")
    reset_backend_modules()

    from Backend.application.market_data_service import select_market_data_provider
    from Backend.infrastructure.market_data.fallback_provider import PaperFallbackProvider

    provider = select_market_data_provider("auto")

    assert isinstance(provider, PaperFallbackProvider)
    assert [item.provider_name for item in provider.providers] == ["dhan", "yahoo"]
    assert provider.live_suitable is False


def test_auto_provider_is_never_allowed_for_live_mode(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    reset_backend_modules()

    from Backend.application.market_data_service import MarketDataService
    from Backend.domain.market_data.provider import MarketDataProviderError
    from Backend.infrastructure.market_data.fallback_provider import PaperFallbackProvider

    service = MarketDataService(PaperFallbackProvider([_provider("dhan")]))

    with pytest.raises(MarketDataProviderError, match="paper only"):
        service.get_ltp("NIFTY", mode="live")


def test_nse_provider_is_explicit_licensed_fail_closed_boundary(monkeypatch):
    monkeypatch.delenv("NSE_DATA_LICENSE_ID", raising=False)

    from Backend.application.market_data_service import select_market_data_provider
    from Backend.domain.market_data.provider import MarketDataProviderError

    provider = select_market_data_provider("nse")

    assert provider.provider_name == "nse"
    assert provider.health_check()["configured"] is False
    with pytest.raises(MarketDataProviderError, match="NSE_DATA_LICENSE_ID"):
        provider.get_ltp("NIFTY")
