from datetime import datetime, timezone

from Backend.application.agents.quantgrid_specialists import (
    network_health_agent, financial_risk_agent, market_research_agent,
)


def test_network_agent_detects_stale_feed():
    result = network_health_agent(api_latency_ms=200, error_rate=0.01,
        redis_ok=True, db_ok=True, worker_lag_seconds=0, market_feed_age_seconds=60)
    assert result["status"] == "degraded"
    assert not result["trading_data_usable"]


def test_finance_agent_never_authorizes_live_trade():
    result = financial_risk_agent(capital_rupees=10000, reserved_rupees=0,
        proposed_premium_rupees=1000, live_enabled=True, kill_switch=False)
    assert not result["approved"]


def test_market_agent_requires_fresh_quote():
    now = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
    args = dict(symbol="NIFTY", spot=24000, futures_price=24020,
        call_oi=100, put_oi=80, iv_percent=14)
    fresh = market_research_agent(**args, quote_timestamp=now.isoformat(), now=now)
    assert fresh["valid"] and fresh["pcr"] == 0.8 and fresh["signal"] == "research_only"
    stale = market_research_agent(**args, quote_timestamp="2026-11-02T08:00:00Z", now=now)
    assert not stale["valid"]
