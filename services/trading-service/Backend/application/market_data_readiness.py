from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from Backend.application.candle_validation import (
    NSE_TIMEZONE,
    CandleValidationSettings,
    get_market_session,
    normalize_timestamp,
    validation_settings,
)


def _is_trading_day(day: date, settings: CandleValidationSettings) -> bool:
    return day.weekday() < 5 and day.isoformat() not in settings.holidays


def _session_close(day: date, settings: CandleValidationSettings) -> datetime:
    return datetime.combine(day, settings.market_close, NSE_TIMEZONE)


def _latest_completed_session_close(
    now: datetime,
    settings: CandleValidationSettings,
) -> datetime:
    local_now = normalize_timestamp(now) or datetime.now(NSE_TIMEZONE)
    today = local_now.date()
    today_close = _session_close(today, settings)

    if _is_trading_day(today, settings) and local_now > today_close:
        return today_close

    candidate = today - timedelta(days=1)
    while not _is_trading_day(candidate, settings):
        candidate -= timedelta(days=1)
    return _session_close(candidate, settings)


def stored_market_data_readiness(
    latest_candle: Any,
    *,
    now: datetime | None = None,
    interval_seconds: int = 60,
    settings: CandleValidationSettings | None = None,
) -> dict[str, Any]:
    settings = settings or validation_settings()
    current = normalize_timestamp(now or datetime.now(timezone.utc)) or datetime.now(NSE_TIMEZONE)
    session = get_market_session(current, settings=settings)
    latest = normalize_timestamp(latest_candle)

    base = {
        "healthy": False,
        "execution_fresh": False,
        "market_live": session.market_live,
        "market_status": session.status,
        "is_trading_day": session.is_trading_day,
        "latest_timestamp": latest.astimezone(timezone.utc).isoformat() if latest else None,
        "latest_timestamp_ist": latest.isoformat() if latest else None,
        "age_seconds": max(0, int((current - latest).total_seconds())) if latest else None,
        "expected_completed_session_close": None,
        "reason": "",
    }

    if latest is None:
        return base | {"reason": "no_latest_candle"}

    if session.market_live:
        max_age = settings.reject_after_seconds + settings.delayed_feed_tolerance_seconds
        fresh = 0 <= (current - latest).total_seconds() <= max_age
        return base | {
            "healthy": fresh,
            "execution_fresh": fresh,
            "max_live_age_seconds": max_age,
            "reason": "live_feed_fresh" if fresh else "live_feed_stale",
        }

    expected_close = _latest_completed_session_close(current, settings)
    # A 1-minute feed commonly stamps the final bar at 15:29 for the 15:30 close.
    tolerance = max(int(interval_seconds), settings.delayed_feed_tolerance_seconds)
    session_current = latest >= expected_close - timedelta(seconds=tolerance)
    return base | {
        "healthy": session_current,
        "execution_fresh": False,
        "expected_completed_session_close": expected_close.astimezone(timezone.utc).isoformat(),
        "expected_completed_session_close_ist": expected_close.isoformat(),
        "completed_session_tolerance_seconds": tolerance,
        "reason": "completed_session_current" if session_current else "completed_session_stale",
    }
