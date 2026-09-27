from __future__ import annotations

import pytest

from Backend.domain.market_data.provider import MarketDataProviderError
from Backend.infrastructure.broker.registry import (
    create_live_broker_adapter,
    registered_broker_adapters,
)
from Backend.infrastructure.market_data.angel_provider import AngelProvider
from Backend.infrastructure.market_data.kite_provider import KiteProvider
from Backend.infrastructure.market_data.registry import (
    create_market_data_provider,
    registered_market_providers,
)


def test_market_data_registry_exposes_current_provider_keys():
    providers = registered_market_providers()

    assert "dhan" in providers
    assert "zerodha" in providers
    assert "upstox" in providers
    assert "fyers" in providers
    assert "angelone" in providers
    assert "yahoo" in providers


def test_market_data_registry_supports_broker_aliases():
    assert isinstance(create_market_data_provider("zerodha"), KiteProvider)
    assert isinstance(create_market_data_provider("angelone"), AngelProvider)
    assert isinstance(create_market_data_provider("smartapi"), AngelProvider)


def test_market_data_registry_rejects_unknown_provider():
    with pytest.raises(MarketDataProviderError, match="Unsupported market data provider"):
        create_market_data_provider("unknown-provider")


def test_live_broker_registry_is_explicit_about_implemented_execution_adapters():
    assert registered_broker_adapters() == ("dhan",)
    assert create_live_broker_adapter("not-implemented") is None
