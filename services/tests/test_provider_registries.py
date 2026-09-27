from __future__ import annotations

import pytest

from Backend.domain.market_data.provider import MarketDataProvider, MarketDataProviderError
from Backend.infrastructure.broker.registry import broker_registry, create_broker_adapter, supported_brokers
from Backend.infrastructure.market_data.registry import (
    PaperFailoverProvider,
    create_market_data_provider,
    supported_market_data_providers,
)


class _FailingProvider(MarketDataProvider):
    provider_name = "primary"
    live_suitable = True

    def get_ltp(self, symbol: str):
        raise MarketDataProviderError("primary unavailable")

    def get_candles(self, symbol: str, interval: str, period: str, limit: int):
        raise MarketDataProviderError("primary unavailable")

    def subscribe_ticks(self, symbols):
        return None

    def normalize_symbol(self, symbol: str):
        return symbol.upper()

    def health_check(self):
        return {"provider": self.provider_name, "healthy": False, "configured": True}


class _FallbackProvider(MarketDataProvider):
    provider_name = "fallback"
    live_suitable = False
    paper_suitable = True

    def get_ltp(self, symbol: str):
        self.mark_fetch()
        return {"symbol": symbol.upper(), "ltp": 100.0, "timestamp": self.latest_fetch_at}

    def get_candles(self, symbol: str, interval: str, period: str, limit: int):
        self.mark_fetch()
        return [
            {
                "symbol": symbol.upper(),
                "timestamp": self.latest_fetch_at,
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
                "volume": 0,
            }
        ]

    def subscribe_ticks(self, symbols):
        raise MarketDataProviderError("paper provider has no tick stream")

    def normalize_symbol(self, symbol: str):
        return symbol.upper()

    def health_check(self):
        return {"provider": self.provider_name, "healthy": True, "configured": True}


def test_market_data_registry_exposes_existing_provider_adapters():
    providers = supported_market_data_providers()

    assert {"dhan", "yahoo", "zerodha", "upstox", "fyers", "angel"}.issubset(providers)
    assert create_market_data_provider("zerodha").provider_name == "kite"
    assert create_market_data_provider("angelone").provider_name == "angel"


def test_paper_failover_uses_secondary_provider_after_primary_failure():
    provider = PaperFailoverProvider([_FailingProvider(), _FallbackProvider()])

    ltp = provider.get_ltp("NIFTY")
    candles = provider.get_candles("NIFTY", "1m", "1d", 100)
    health = provider.health_check()

    assert ltp["ltp"] == 100.0
    assert candles
    assert provider.provider_name == "fallback"
    assert provider.live_suitable is False
    assert health["failover_used"] is True
    assert health["fallback_chain"] == ["primary", "fallback"]
    assert any(item["provider"] == "primary" for item in health["failures"])


def test_broker_registry_separates_implemented_and_planned_adapters():
    assert supported_brokers(implemented_only=True) == ("dhan",)
    assert {"dhan", "zerodha", "upstox", "fyers", "angel"}.issubset(supported_brokers())
    assert broker_registry()["kite"].name == "zerodha"

    with pytest.raises(RuntimeError, match="future integration"):
        create_broker_adapter("zerodha")
