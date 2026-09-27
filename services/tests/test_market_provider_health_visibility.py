from __future__ import annotations

from datetime import datetime, timezone

from Backend.domain.market_data.provider import MarketDataProvider


class _StatefulProvider(MarketDataProvider):
    paper_suitable = True

    def __init__(self, *, live_suitable: bool, failover: bool = False) -> None:
        self.live_suitable = live_suitable
        self.failover = failover
        self.active = "dhan"

    @property
    def provider_name(self) -> str:
        return self.active

    def get_ltp(self, symbol: str):
        raise AssertionError("test replaces service probe")

    def get_candles(self, symbol: str, interval: str, period: str, limit: int):
        raise AssertionError("test replaces service probe")

    def subscribe_ticks(self, symbols):
        return None

    def normalize_symbol(self, symbol: str):
        return symbol.upper()

    def health_check(self):
        failover_used = self.failover and self.active != "dhan"
        return {
            "provider": self.active,
            "provider_name": self.active,
            "healthy": True,
            "configured": True,
            "connected": True,
            "fallback_chain": ["dhan", "yahoo"] if self.failover else [self.active],
            "failover_used": failover_used,
        }


def _configure(monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_PROVIDER", "dhan")
    reset_backend_modules()


def test_health_reports_provider_selected_during_probe(monkeypatch):
    _configure(monkeypatch)

    from Backend.application.market_data_service import MarketDataService

    provider = _StatefulProvider(live_suitable=False, failover=True)
    service = MarketDataService(provider=provider)
    now = datetime.now(timezone.utc).isoformat()

    def fake_ltp(*_args, **_kwargs):
        provider.active = "yahoo"
        return {
            "timestamp": now,
            "cache_status": "fresh",
            "feed_delay_seconds": 0,
        }

    monkeypatch.setattr(service, "get_ltp", fake_ltp)
    monkeypatch.setattr(
        service,
        "get_candles",
        lambda *_args, **_kwargs: {
            "latest_fetch_at": now,
            "fresh": True,
            "cache_status": "fresh",
            "feed_delay_seconds": 0,
        },
    )

    health = service.health("NIFTY", "1m")

    assert health["configured_provider"] == "dhan"
    assert health["active_provider"] == "yahoo"
    assert health["fallback_chain"] == ["dhan", "yahoo"]
    assert health["failover_used"] is True
    assert health["provider_mode"] == "failover"
    assert health["degraded"] is True
    assert health["execution_eligible"] is False
    assert health["status_reason"] == "paper_failover_active"
    assert health["fresh"] is True


def test_health_marks_fresh_primary_live_provider_execution_eligible(monkeypatch):
    _configure(monkeypatch)

    from Backend.application.market_data_service import MarketDataService

    provider = _StatefulProvider(live_suitable=True)
    service = MarketDataService(provider=provider)
    now = datetime.now(timezone.utc).isoformat()

    monkeypatch.setattr(
        service,
        "get_ltp",
        lambda *_args, **_kwargs: {
            "timestamp": now,
            "cache_status": "fresh",
            "feed_delay_seconds": 0,
        },
    )
    monkeypatch.setattr(
        service,
        "get_candles",
        lambda *_args, **_kwargs: {
            "latest_fetch_at": now,
            "fresh": True,
            "cache_status": "fresh",
            "feed_delay_seconds": 0,
        },
    )

    health = service.health("NIFTY", "1m")

    assert health["active_provider"] == "dhan"
    assert health["provider_mode"] == "primary"
    assert health["failover_used"] is False
    assert health["degraded"] is False
    assert health["execution_eligible"] is True
    assert health["status_reason"] == "healthy"


def test_provider_status_endpoint_preserves_failover_diagnostics(monkeypatch):
    _configure(monkeypatch)

    from Backend.presentation.api import market_api

    class FakeService:
        def health(self, symbol: str = "NIFTY", interval: str = "1m"):
            return {
                "provider": "yahoo",
                "provider_name": "yahoo",
                "configured_provider": "dhan",
                "active_provider": "yahoo",
                "fallback_chain": ["dhan", "yahoo"],
                "failover_used": True,
                "provider_mode": "failover",
                "paper_suitable": True,
                "live_suitable": False,
                "execution_eligible": False,
                "degraded": True,
                "status_reason": "paper_failover_active",
                "latest_fetch_at": "2026-09-27T08:30:00+00:00",
                "fresh": True,
                "stale": False,
            }

    monkeypatch.setattr(market_api, "get_market_data_service", lambda: FakeService())

    result = market_api.get_market_provider_status(_role="viewer")

    assert result["configured_provider"] == "dhan"
    assert result["active_provider"] == "yahoo"
    assert result["failover_used"] is True
    assert result["provider_mode"] == "failover"
    assert result["suitability"] == "paper"
    assert result["freshness"] == "fresh"
