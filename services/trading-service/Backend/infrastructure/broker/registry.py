from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


BrokerFactory = Callable[[], Any]


@dataclass(frozen=True)
class BrokerRegistration:
    name: str
    implemented: bool
    factory: BrokerFactory | None = None
    aliases: tuple[str, ...] = ()


def _dhan_factory():
    from Backend.infrastructure.broker.dhan_order_adapter import DhanBrokerClient
    return DhanBrokerClient()


_REGISTRATIONS = (
    BrokerRegistration("dhan", True, _dhan_factory),
    BrokerRegistration("zerodha", False, aliases=("kite",)),
    BrokerRegistration("upstox", False),
    BrokerRegistration("fyers", False),
    BrokerRegistration("angel", False, aliases=("angelone", "smartapi")),
)


def broker_registry() -> dict[str, BrokerRegistration]:
    registry: dict[str, BrokerRegistration] = {}
    for registration in _REGISTRATIONS:
        registry[registration.name] = registration
        for alias in registration.aliases:
            registry[alias] = registration
    return registry


def supported_brokers(*, implemented_only: bool = False) -> tuple[str, ...]:
    registrations = {
        registration.name: registration for registration in _REGISTRATIONS
    }
    return tuple(
        sorted(
            name
            for name, registration in registrations.items()
            if registration.implemented or not implemented_only
        )
    )


def create_broker_adapter(name: str):
    normalized = (name or "").strip().lower()
    registration = broker_registry().get(normalized)
    if registration is None:
        raise RuntimeError(
            f"Unsupported broker provider: {normalized or '<empty>'}. "
            f"Known providers: {', '.join(supported_brokers())}."
        )
    if not registration.implemented or registration.factory is None:
        raise RuntimeError(
            f"Broker adapter '{registration.name}' is registered for future integration "
            "but live execution is not implemented."
        )
    return registration.factory()
