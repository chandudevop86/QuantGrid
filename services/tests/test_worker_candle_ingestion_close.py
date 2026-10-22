from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from Backend.application import worker


IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.parametrize("hour,minute,expected", [
    (9, 14, False),
    (9, 15, True),
    (15, 29, True),
    (15, 30, True),
    (15, 34, True),
    (15, 35, True),
    (15, 36, False),
])
def test_postclose_ingestion_window(hour, minute, expected):
    now = datetime(2026, 10, 22, hour, minute, tzinfo=IST)
    assert worker._candle_ingestion_session_allowed(now) is expected


@pytest.mark.parametrize("day", [17, 18, 20])
def test_no_ingestion_on_weekend_or_nse_holiday(day):
    now = datetime(2026, 10, day, 15, 32, tzinfo=IST)
    assert worker._candle_ingestion_session_allowed(now) is False


def test_no_ingestion_after_close_grace_period():
    now = datetime(2026, 10, 22, 15, 35, 1, tzinfo=IST)
    assert worker._candle_ingestion_session_allowed(now) is False


def test_ingestion_skip_does_not_fetch_outside_window(monkeypatch):
    monkeypatch.setattr(worker, "_candle_market_hours_only", lambda: True)
    monkeypatch.setattr(worker, "_candle_ingestion_session_allowed", lambda: False)

    def unexpected_fetch():
        raise AssertionError("Provider must not be called outside ingestion window")

    monkeypatch.setattr(worker, "get_market_data_service", unexpected_fetch)
    worker._run_candle_ingestion()
