from __future__ import annotations

from typing import Any, Iterable

from Backend.domain.market_data.provider import MarketDataProvider, MarketDataProviderError


class PaperFailoverProvider(MarketDataProvider):
    """Paper-only provider chain.

    The configured provider remains primary. Backup providers are tried only when
    the primary raises or returns unusable data. This adapter is deliberately not
    live-suitable so it cannot silently become an execution-quality market feed.
    """

    provider_name = "paper-failover"
    live_suitable = False
    paper_suitable = True
    warning = "Paper-mode market-data failover is active; fallback data is not approved for live execution."

    def __init__(
        self,
        primary: MarketDataProvider,
        fallbacks: list[MarketDataProvider],
    ) -> None:
        self.primary = primary
        self.fallbacks = list(fallbacks)
        self.selected_provider_name = primary.provider_name
        self.failover_used = False
        self.last_errors: list[str] = []

    def _candidates(self) -> list[MarketDataProvider]:
        return [self.primary, *self.fallbacks]

    def _select(self, provider: MarketDataProvider, *, failover_used: bool) -> None:
        self.selected_provider_name = provider.provider_name
        self.failover_used = failover_used
        self.latest_fetch_at = getattr(provider, "latest_fetch_at", None)

    def get_ltp(self, symbol: str) -> dict[str, Any]:
        errors: list[str] = []
        for index, provider in enumerate(self._candidates()):
            try:
                payload = provider.get_ltp(symbol)
                value = payload.get("ltp", payload.get("price"))
                if value in (None, "") or float(value) <= 0:
                    raise MarketDataProviderError("Market data LTP is zero or missing.")
                self._select(provider, failover_used=index > 0)
                self.last_errors = errors
                return {
                    **payload,
                    "provider": provider.provider_name,
                    "provider_name": provider.provider_name,
                    "primary_provider": self.primary.provider_name,
                    "failover_used": index > 0,
                }
            except Exception as exc:
                errors.append(f"{provider.provider_name}: {exc}")

        self.last_errors = errors
        raise MarketDataProviderError(
            "All paper market-data providers failed: " + "; ".join(errors)
        )

    def get_candles(
        self,
        symbol: str,
        interval: str,
        period: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        errors: list[str] = []
        for index, provider in enumerate(self._candidates()):
            try:
                candles = provider.get_candles(symbol, interval, period, limit)
                if not candles:
                    raise MarketDataProviderError("Market data provider returned no candles.")
                self._select(provider, failover_used=index > 0)
                self.last_errors = errors
                return candles
            except Exception as exc:
                errors.append(f"{provider.provider_name}: {exc}")

        self.last_errors = errors
        raise MarketDataProviderError(
            "All paper market-data providers failed: " + "; ".join(errors)
        )

    def subscribe_ticks(self, symbols: Iterable[str]) -> None:
        raise MarketDataProviderError(
            "Paper failover does not provide a live tick subscription."
        )

    def normalize_symbol(self, symbol: str) -> str:
        for provider in self._candidates():
            if provider.provider_name == self.selected_provider_name:
                return provider.normalize_symbol(symbol)
        return self.primary.normalize_symbol(symbol)

    def health_check(self) -> dict[str, Any]:
        primary_status = self.primary.health_check()
        fallback_status = [provider.health_check() for provider in self.fallbacks]
        configured = bool(
            primary_status.get("configured")
            or any(status.get("configured", True) for status in fallback_status)
        )
        healthy = bool(
            primary_status.get("healthy")
            or any(status.get("healthy") for status in fallback_status)
        )
        return self.status_payload() | {
            "configured": configured,
            "connected": bool(primary_status.get("connected")),
            "healthy": healthy,
            "primary_provider": self.primary.provider_name,
            "selected_provider": self.selected_provider_name,
            "failover_used": self.failover_used,
            "primary_status": primary_status,
            "fallback_status": fallback_status,
        }
