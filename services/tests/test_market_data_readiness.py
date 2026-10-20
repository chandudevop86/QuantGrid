from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from Backend.application.candle_validation import CandleValidationSettings
from Backend.application.market_data_readiness import stored_market_data_readiness


IST = ZoneInfo("Asia/Kolkata")


def test_holiday_accepts_latest_completed_session_candle():
    settings = CandleValidationSettings(holidays={"2026-10-20"})
    now = datetime(2026, 10, 20, 12, 0, tzinfo=IST)
    latest = datetime(2026, 10, 19, 15, 29, tzinfo=IST)

    result = stored_market_data_readiness(latest, now=now, settings=settings)

    assert result["healthy"] is True
    assert result["execution_fresh"] is False
    assert result["market_status"] == "HOLIDAY"
    assert result["reason"] == "completed_session_current"


def test_holiday_rejects_old_completed_session_data():
    settings = CandleValidationSettings(holidays={"2026-10-20"})
    now = datetime(2026, 10, 20, 12, 0, tzinfo=IST)
    latest = datetime(2026, 10, 16, 15, 29, tzinfo=IST)

    result = stored_market_data_readiness(latest, now=now, settings=settings)

    assert result["healthy"] is False
    assert result["execution_fresh"] is False
    assert result["reason"] == "completed_session_stale"


def test_after_close_requires_current_sessions_final_candle():
    settings = CandleValidationSettings(holidays=set())
    now = datetime(2026, 10, 19, 16, 0, tzinfo=IST)
    latest = datetime(2026, 10, 19, 15, 29, tzinfo=IST)

    result = stored_market_data_readiness(latest, now=now, settings=settings)

    assert result["healthy"] is True
    assert result["market_status"] == "MARKET CLOSED"
    assert result["execution_fresh"] is False


def test_live_session_requires_recent_candle_for_execution():
    settings = CandleValidationSettings(
        holidays=set(),
        reject_after_seconds=300,
        delayed_feed_tolerance_seconds=60,
    )
    now = datetime(2026, 10, 19, 10, 0, tzinfo=IST)
    latest = now - timedelta(minutes=7)

    result = stored_market_data_readiness(latest, now=now, settings=settings)

    assert result["healthy"] is False
    assert result["execution_fresh"] is False
    assert result["market_status"] == "LIVE MARKET"
    assert result["reason"] == "live_feed_stale"


def test_live_session_accepts_recent_candle_for_execution():
    settings = CandleValidationSettings(
        holidays=set(),
        reject_after_seconds=300,
        delayed_feed_tolerance_seconds=60,
    )
    now = datetime(2026, 10, 19, 10, 0, tzinfo=IST)
    latest = now - timedelta(seconds=90)

    result = stored_market_data_readiness(latest, now=now, settings=settings)

    assert result["healthy"] is True
    assert result["execution_fresh"] is True
    assert result["reason"] == "live_feed_fresh"
