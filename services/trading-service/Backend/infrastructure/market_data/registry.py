from __future__ import annotations

from collections.abc import Callable

from Backend.domain.market_data.provider import MarketDataProvider, MarketDataProviderError
from Backend.infrastructure.market_data import (
    AngelProvider,
    DhanProvider,
    FyersProvider,
    KiteProvider,
    UpstoxProvider,
    YahooProvider,
)

ProviderFactory = Callable[[], MarketDataProvider]

_PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "yahoo": YahooProvider,
    "kite": KiteProvider,
    "zerodha": KiteProvider,
    "upstox": UpstoxProvider,
    "dhan": DhanProvider,
    "fyers": FyersProvider,
    "angel": AngelProvider,
    "angelone": AngelProvider,
    "smartapi": AngelProvider,
}


def normalize_market_provider_name(name: str | None) -> str:
    return (name or "dhan").strip().lower()


def registered_market_providers() -> tuple[str, ...]:
    """Return configured provider keys without instantiating provider clients."""
    return tuple(sorted(_PROVIDER_FACTORIES))


def create_market_data_provider(name: str | None) -> MarketDataProvider:
    """Create a market-data adapter by provider key.

    This registry keeps strategy/application code independent from concrete broker
    SDKs. A future licensed NSE/vendor feed can be added by registering its adapter
    here without changing strategy code.
    """
    provider = normalize_market_provider_name(name)
    factory = _PROVIDER_FACTORIES.get(provider)
    if factory is None:
        supported = ", ".join(registered_market_providers())
        raise MarketDataProviderError(
            f"Unsupported market data provider: {provider}. Supported providers: {supported}"
        )
    return factory()
