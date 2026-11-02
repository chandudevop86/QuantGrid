from datetime import datetime, timezone
from Backend.application.agents.market_analyst_v2 import analyze_derivatives


def test_research_metrics_not_order_signal():
    now = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
    args = dict(symbol="NIFTY", spot=24000, future=24030, call_oi=100,
                put_oi=90, call_iv=13, put_iv=15)
    result = analyze_derivatives(**args, quote_timestamp=now.isoformat(), now=now)
    assert result["valid"] and result["pcr"] == 0.9
    assert result["recommendation"] == "none"


def test_stale_market_data_rejected():
    now = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
    result = analyze_derivatives(symbol="NIFTY", spot=24000, future=24030,
        call_oi=100, put_oi=90, call_iv=13, put_iv=15,
        quote_timestamp="2026-11-02T08:00:00Z", now=now)
    assert not result["valid"]
