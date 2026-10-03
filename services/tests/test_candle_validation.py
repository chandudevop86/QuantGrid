from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from Backend.application.candle_validation import (
    CandleValidationSettings,
    detect_feed_delay,
    get_market_session,
    normalize_timestamp,
    validate_live_candle,
)


IST = ZoneInfo("Asia/Kolkata")


def test_normalize_timestamp_handles_naive_utc_and_localized_values():
    naive = normalize_timestamp("2026-05-22T09:20:00")
    utc = normalize_timestamp("2026-05-22T03:50:00+00:00")
    localized = normalize_timestamp(datetime(2026, 5, 22, 9, 20, tzinfo=IST))

    assert naive.isoformat() == "2026-05-22T09:20:00+05:30"
    assert utc.isoformat() == "2026-05-22T09:20:00+05:30"
    assert localized.isoformat() == "2026-05-22T09:20:00+05:30"


def test_live_market_rejects_beyond_threshold_plus_tolerance():
    now = datetime(2026, 5, 22, 10, 0, tzinfo=IST)
    latest = now - timedelta(minutes=7)
    result = validate_live_candle(
        [{"timestamp": latest.isoformat(), "open": 1, "high": 2, "low": 1, "close": 2}],
        interval="1m",
        now=now,
        settings=CandleValidationSettings(reject_after_seconds=300, delayed_feed_tolerance_seconds=60),
    )

    assert result.valid is False
    assert result.market_live is True
    assert result.market_status == "DELAYED FEED"
    assert result.delay_seconds == 420
    assert result.diagnostics


def test_live_market_warns_but_allows_delayed_feed_inside_tolerance():
    now = datetime(2026, 5, 22, 10, 0, tzinfo=IST)
    latest = now - timedelta(minutes=3)
    result = validate_live_candle(
        [{"timestamp": latest.isoformat(), "open": 1, "high": 2, "low": 1, "close": 2}],
        interval="1m",
        now=now,
        settings=CandleValidationSettings(warning_after_seconds=120, reject_after_seconds=300),
    )

    assert result.valid is True
    assert result.market_status == "DELAYED FEED"
    assert "Feed delay is 180s" in result.warnings[0]


def test_after_market_close_allows_final_candle_analysis():
    now = datetime(2026, 5, 22, 16, 5, tzinfo=IST)
    latest = datetime(2026, 5, 22, 15, 30, tzinfo=IST)
    result = validate_live_candle(
        [{"timestamp": latest.isoformat(), "open": 1, "high": 2, "low": 1, "close": 2}],
        now=now,
    )

    assert result.valid is True
    assert result.market_live is False
    assert result.market_status == "MARKET CLOSED"
    assert "stale rejection disabled" in result.warnings[0]


def test_weekend_and_holiday_disable_stale_rejection():
    weekend = validate_live_candle(
        [{"timestamp": "2026-05-22T15:30:00+05:30", "open": 1, "high": 2, "low": 1, "close": 2}],
        now=datetime(2026, 5, 23, 10, 0, tzinfo=IST),
    )
    holiday = validate_live_candle(
        [{"timestamp": "2026-05-22T15:30:00+05:30", "open": 1, "high": 2, "low": 1, "close": 2}],
        now=datetime(2026, 5, 22, 10, 0, tzinfo=IST),
        settings=CandleValidationSettings(holidays={"2026-05-22"}),
    )

    assert weekend.valid is True
    assert weekend.market_status == "WEEKEND"
    assert holiday.valid is True
    assert holiday.market_status == "HOLIDAY"


def test_feed_delay_reports_missing_candles_and_provider_latency():
    now = datetime(2026, 5, 22, 10, 0, tzinfo=IST)
    delay = detect_feed_delay(
        now - timedelta(minutes=4),
        now=now,
        interval="1m",
        provider_fetched_at=now - timedelta(seconds=2),
    )

    assert delay.delay_seconds == 240
    assert delay.provider_latency_seconds == 2
    assert delay.missing_candles == 3


def test_default_nse_2026_equities_holidays_and_open_days(monkeypatch):
    monkeypatch.delenv("QUANTGRID_NSE_HOLIDAYS", raising=False)
    from Backend.application.candle_validation import DEFAULT_NSE_HOLIDAYS, validation_settings

    expected = {
        "2026-01-15", "2026-01-26", "2026-03-03", "2026-03-26",
        "2026-03-31", "2026-04-03", "2026-04-14", "2026-05-01",
        "2026-05-28", "2026-06-26", "2026-09-14", "2026-10-02",
        "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25",
    }
    assert DEFAULT_NSE_HOLIDAYS == expected
    settings = validation_settings()
    for day in expected:
        session = get_market_session(datetime.fromisoformat(day + "T10:00:00+05:30"), settings=settings)
        assert session.status == "HOLIDAY", day
        assert not session.market_live
    # The former incorrect holiday must not block an otherwise normal weekday.
    for day in ("2026-10-05", "2026-11-09"):
        session = get_market_session(datetime.fromisoformat(day + "T10:00:00+05:30"), settings=settings)
        assert session.status == "LIVE MARKET", day
        assert session.market_live
