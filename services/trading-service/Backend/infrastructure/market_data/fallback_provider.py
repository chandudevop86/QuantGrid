from __future__ import annotations

from typing import Any, Iterable

from Backend.domain.market_data.provider import MarketDataProvider, MarketDataProviderError


class PaperFallbackProvider(MarketDataProvider):
    """Try configured providers in order for paper/analysis workloads only.

    This adapter is deliberately not live-suitable. A live deployment must select
    one explicit trading-grade provider so a demo fallback can never silently
    become an execution data source.
    """

    provider_name = "auto"
    live_suitable = False
    paper_suitable = True
    warning = "Automatic provider failover is paper/analysis only."

    def __init__(self, providers: list[MarketDataProvider]) -> None:
        if not providers:
            raise ValueError("PaperFallbackProvider requires at least one provider.")
        self.providers = providers
        self.active_provider_name: str | None = None
        self.failures: list[str] = []

    def _configured(self, provider: MarketDataProvider) -> bool:
        try:
            status = provider.health_check()
        except Exception:
            return True
        return bool(status.get("configured", True))

    def _call(self, method: str, *args: Any) -> Any:
        failures: list[str] = []
        for provider in self.providers:
            if not self._configured(provider):
                failures.append(f"{provider.provider_name}: not configured")
                continue
            try:
                result = getattr(provider, method)(*args)
                if method == "get_candles" and not result:
                    raise MarketDataProviderError("provider returned no candles")
            except Exception as exc:
                failures.append(f"{provider.provider_name}: {exc}")
                continue

            self.active_provider_name = provider.provider_name
            self.latest_fetch_at = getattr(provider, "latest_fetch_at", None)
            self.failures = failures
            if method == "get_ltp" and isinstance(result, dict):
                return {
                    **result,
                    "provider": provider.provider_name,
                    "provider_name": provider.provider_name,
                    "fallback_used": provider is not self.providers[0],
                }
            return result

        self.active_provider_name = None
        self.failures = failures
        detail = "; ".join(failures) if failures else "no providers available"
        raise MarketDataProviderError(f"All paper market data providers failed: {detail}")

    def get_ltp(self, symbol: str) -> dict[str, Any]:
        return self._call("get_ltp", symbol)

    def get_candles(
        self,
        symbol: str,
        interval: str,
        period: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        return self._call("get_candles", symbol, interval, period, limit)

    def subscribe_ticks(self, symbols: Iterable[str]) -> None:
        raise MarketDataProviderError(
            "Automatic provider failover is paper/analysis only; select an explicit live provider for tick streaming."
        )

    def normalize_symbol(self, symbol: str) -> str:
        active = next(
            (provider for provider in self.providers if provider.provider_name == self.active_provider_name),
            self.providers[0],
        )
        return active.normalize_symbol(symbol)

    def health_check(self) -> dict[str, Any]:
        children: list[dict[str, Any]] = []
        any_configured = False
        for provider in self.providers:
            try:
                status = provider.health_check()
            except Exception as exc:
                status = {
                    "provider": provider.provider_name,
                    "configured": False,
                    "healthy": False,
                    "message": str(exc),
                }
            any_configured = any_configured or bool(status.get("configured", True))
            children.append(
                {
                    "provider": provider.provider_name,
                    "configured": bool(status.get("configured", True)),
                    "healthy": bool(status.get("healthy", False)),
                }
            )

        return self.status_payload() | {
            "configured": any_configured,
            "connected": self.active_provider_name is not None,
            "healthy": any_configured,
            "active_provider": self.active_provider_name,
            "provider_chain": [provider.provider_name for provider in self.providers],
            "providers": children,
            "message": "Paper provider failover configured." if any_configured else "No paper market data provider is configured.",
        }
