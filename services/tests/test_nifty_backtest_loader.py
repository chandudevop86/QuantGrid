"""Guard NIFTY backtest extraction against interval and timezone regressions."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from Backend.trading_system import backtest_loader


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeSession:
    def __init__(self, rows, recorded):
        self.rows = rows
        self.recorded = recorded

    def execute(self, sql, params):
        self.recorded.append((str(sql), params))
        return FakeResult(self.rows)


def test_load_nifty_reads_1m_and_includes_last_ist_day(monkeypatch):
    rows = [
        (datetime(2026, 10, 16, 3, 45, tzinfo=timezone.utc), 23000, 23010, 22990, 23005, None),
        (datetime(2026, 10, 16, 9, 55, tzinfo=timezone.utc), 23005, 23015, 23000, 23010, 500),
    ]
    recorded = []

    @contextmanager
    def session():
        yield FakeSession(rows, recorded)

    monkeypatch.setattr(backtest_loader, "SessionLocal", session)
    result = backtest_loader.load_nifty_candles("2026-10-01", "2026-10-16")
    assert len(result) == 2
    assert result["timestamp"].dt.tz is not None
    assert result["volume"].tolist() == [0, 500]
    query, params = recorded[0]
    assert "interval IN ('1m', '1')" in query
    assert "timestamp < :end_exclusive" in query
    assert params["start"].isoformat() == "2026-09-30T18:30:00+00:00"
    assert params["end_exclusive"].isoformat() == "2026-10-16T18:30:00+00:00"


def test_load_nifty_empty_range_returns_empty(monkeypatch):
    @contextmanager
    def session():
        yield FakeSession([], [])

    monkeypatch.setattr(backtest_loader, "SessionLocal", session)
    df = backtest_loader.load_nifty_candles("2026-10-01", "2026-10-16")
    assert df.empty
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]


def test_load_nifty_rejects_reversed_dates():
    import pytest

    with pytest.raises(ValueError, match="end_date"):
        backtest_loader.load_nifty_candles("2026-10-16", "2026-10-01")
