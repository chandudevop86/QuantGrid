from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Iterable

from Backend.domain.market_data.provider import MarketDataProvider, MarketDataProviderError


ProviderFactory = Callable[[], MarketDataProvider]


def _provider_factories() -> dict[str, ProviderFactory]:
    # Lazy imports keep provider SDKs isolated until a provider is selected.
    from Backend.infrastructure.market_data.angel_provider import AngelProvider
    from Backend.infrastructure.market_data.dhan_provider import DhanProvider
    from Backend.infrastructure.market_data.fyers_provider import FyersProvider
    from Backend.infrastructure.market_data.kite_provider import KiteProvider
    from Backend.infrastructure.market_data.upstox_provider import UpstoxProvider
    from Backend.infrastructure.market_data.yahoo_provider import YahooProvider

    return {
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


def supported_market_data_providers() -> tuple[str, ...]:
    return tuple(sorted(_provider_factories()))


def create_market_data_provider(name: str) -> MarketDataProvider:
    normalized = (name or "dhan").strip().lower()
    factory = _provider_factories().get(normalized)
    if factory is None:
        supported = ", ".join(supported_market_data_providers())
        raise MarketDataProviderError(
            f"Unsupported market data provider: {normalized}. Supported providers: {supported}"
        )
    return factory()


def configured_paper_fallback_names(primary_name: str) -> tuple[str, ...]:
    configured = os.getenv("QUANTGRID_MARKET_DATA_FALLBACKS")
    raw = "yahoo" if configured is None else configured
    primary = (primary_name or "").strip().lower()
    names: list[str] = []
    for item in raw.split(","):
        name = item.strip().lower()
        if not name or name == primary or name in names:
            continue
        names.append(name)
    return tuple(names)


@dataclass(frozen=True)
class ProviderFailure:
    provider: str
    error: str


class PaperFailoverProvider(MarketDataProvider):
    """Paper-analysis provider chain.

    This wrapper is deliberately never live-suitable. It allows QuantGrid to keep
    paper analysis available when a broker market-data session expires, while the
    live-execution guardrails continue to reject the chain.
    """

    live_suitable = False
    paper_suitable = True

    def __init__(self, providers: Iterable[MarketDataProvider]) -> None:
        self.providers = list(providers)
        if not self.providers:
            raise ValueError("PaperFailoverProvider requires at least one provider.")
        self._active = self.providers[0]
        self.failures: list[ProviderFailure] = []
        self.warning = "Paper-mode failover may use non-trading-grade data; never use this chain for live execution."
        self.latest_fetch_at = None

    @property
    def provider_name(self) -> str:
        return self._active.provider_name

    def _record_success(self, provider: MarketDataProvider) -> None:
        self._active = provider
        self.latest_fetch_at = getattr(provider, "latest_fetch_at", None)

    def get_ltp(self, symbol: str) -> dict:
        failures: list[ProviderFailure] = []
        for provider in self.providers:
            try:
                payload = provider.get_ltp(symbol)
                ltp = payload.get("ltp", payload.get("price"))
                if ltp in {None, ""} or float(ltp) <= 0:
                    raise MarketDataProviderError("Market data LTP is zero or missing.")
                self._record_success(provider)
                self.failures = failures
                return payload
            except Exception as exc:
                failures.append(ProviderFailure(provider.provider_name, str(exc)))
        self.failures = failures
        raise MarketDataProviderError(self._failure_message("LTP", failures))

    def get_candles(self, symbol: str, interval: str, period: str, limit: int) -> list[dict]:
        failures: list[ProviderFailure] = []
        for provider in self.providers:
            try:
                candles = provider.get_candles(symbol, interval, period, limit)
                if not candles:
                    raise MarketDataProviderError("Market data provider returned no candles.")
                self._record_success(provider)
                self.failures = failures
                return candles
            except Exception as exc:
                failures.append(ProviderFailure(provider.provider_name, str(exc)))
        self.failures = failures
        raise MarketDataProviderError(self._failure_message("candles", failures))

    def subscribe_ticks(self, symbols) -> None:
        raise MarketDataProviderError(
            "Paper failover providers do not expose a live tick subscription."
        )

    def normalize_symbol(self, symbol: str) -> str:
        return self._active.normalize_symbol(symbol)

    def health_check(self) -> dict:
        providers: list[dict] = []
        for provider in self.providers:
            try:
                status = provider.health_check()
            except Exception as exc:
                status = {
                    "provider": provider.provider_name,
                    "healthy": False,
                    "connected": False,
                    "error": str(exc),
                }
            providers.append(status)
        active_status = next(
            (item for item in providers if item.get("provider") == self.provider_name),
            providers[0],
        )
        return self.status_payload() | {
            "configured": any(item.get("configured", True) for item in providers),
            "connected": bool(active_status.get("connected", False)),
            "healthy": any(item.get("healthy", False) for item in providers),
            "message": f"Paper failover chain active provider: {self.provider_name}.",
            "fallback_chain": [provider.provider_name for provider in self.providers],
            "provider_health": providers,
            "failover_used": self._active is not self.providers[0],
            "failures": [
                {"provider": failure.provider, "error": failure.error}
                for failure in self.failures
            ],
        }

    @staticmethod
    def _failure_message(operation: str, failures: list[ProviderFailure]) -> str:
        details = "; ".join(
            f"{failure.provider}: {failure.error}" for failure in failures
        )
        return f"All paper market-data providers failed for {operation}: {details}"


def create_paper_market_data_provider(primary_name: str) -> MarketDataProvider:
    primary = create_market_data_provider(primary_name)
    fallback_names = configured_paper_fallback_names(primary_name)
    fallbacks: list[MarketDataProvider] = []
    for name in fallback_names:
        try:
            fallbacks.append(create_market_data_provider(name))
        except MarketDataProviderError:
            # Invalid fallback names should not prevent the configured primary
            # provider from starting. They are surfaced by configuration tests.
            continue
    if not fallbacks:
        return primary
    return PaperFailoverProvider([primary, *fallbacks])
