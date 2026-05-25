from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from Backend.application.candle_validation import CandleValidationSettings, validate_live_candle

IST = ZoneInfo("Asia/Kolkata")


def test_market_closed_paper_simulation_allows_analysis_not_execution():
    now = datetime(2026, 5, 22, 16, 10, tzinfo=IST)
    latest = datetime(2026, 5, 22, 15, 30, tzinfo=IST)

    result = validate_live_candle(
        [{"timestamp": latest.isoformat(), "open": 1, "high": 2, "low": 1, "close": 2}],
        mode="paper",
        now=now,
    )

    assert result.valid_for_analysis is True
    assert result.valid_for_execution is False
    assert result.market_status == "MARKET CLOSED"


def test_live_execution_blocked_after_market_close():
    now = datetime(2026, 5, 22, 16, 10, tzinfo=IST)
    latest = datetime(2026, 5, 22, 15, 30, tzinfo=IST)

    result = validate_live_candle(
        [{"timestamp": latest.isoformat(), "open": 1, "high": 2, "low": 1, "close": 2}],
        mode="live",
        now=now,
    )

    assert result.valid is True
    assert result.valid_for_execution is False
    assert result.market_live is False


def test_stale_candle_rejected_in_live_mode():
    now = datetime(2026, 5, 22, 10, 0, tzinfo=IST)
    latest = now - timedelta(minutes=8)

    result = validate_live_candle(
        [{"timestamp": latest.isoformat(), "open": 1, "high": 2, "low": 1, "close": 2}],
        mode="live",
        interval="1m",
        now=now,
        settings=CandleValidationSettings(reject_after_seconds=300, delayed_feed_tolerance_seconds=60),
    )

    assert result.valid is False
    assert result.valid_for_execution is False
    assert result.market_status == "DELAYED FEED"


def test_delayed_feed_warning_works_inside_tolerance():
    now = datetime(2026, 5, 22, 10, 0, tzinfo=IST)
    latest = now - timedelta(minutes=3)

    result = validate_live_candle(
        [{"timestamp": latest.isoformat(), "open": 1, "high": 2, "low": 1, "close": 2}],
        mode="live",
        interval="1m",
        now=now,
        settings=CandleValidationSettings(warning_after_seconds=120, reject_after_seconds=300),
    )

    assert result.valid is True
    assert result.valid_for_execution is False
    assert result.market_status == "DELAYED FEED"
    assert result.warnings
