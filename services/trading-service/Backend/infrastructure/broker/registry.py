from __future__ import annotations

from collections.abc import Callable
from typing import Any

BrokerFactory = Callable[[], Any]


def _dhan_factory() -> Any:
    # Lazy import avoids coupling the generic broker registry to the concrete
    # adapter's result types during module initialization.
    from Backend.infrastructure.broker.dhan_order_adapter import DhanBrokerClient

    return DhanBrokerClient()


_BROKER_FACTORIES: dict[str, BrokerFactory] = {
    "dhan": _dhan_factory,
}


def normalize_broker_provider_name(name: str | None) -> str:
    return (name or "").strip().lower()


def registered_broker_adapters() -> tuple[str, ...]:
    """Return live broker adapters implemented for order execution."""
    return tuple(sorted(_BROKER_FACTORIES))


def create_live_broker_adapter(name: str | None) -> Any | None:
    """Create a concrete live broker adapter, or None when not implemented.

    Adding Zerodha/Kite, Upstox, Angel One, Fyers, or another broker should only
    require registering an adapter here once that adapter implements QuantGrid's
    BrokerClient contract and passes the live-trading safety tests.
    """
    provider = normalize_broker_provider_name(name)
    factory = _BROKER_FACTORIES.get(provider)
    return factory() if factory else None
