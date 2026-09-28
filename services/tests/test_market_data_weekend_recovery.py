from __future__ import annotations

from datetime import date

from Backend.infrastructure.market_data import dhan_provider
from Backend.infrastructure.market_data.registry import configured_paper_fallback_names


def test_paper_market_data_defaults_to_yahoo_fallback_when_unset(monkeypatch):
    monkeypatch.delenv("QUANTGRID_MARKET_DATA_FALLBACKS", raising=False)

    assert configured_paper_fallback_names("dhan") == ("yahoo",)


def test_paper_market_data_explicit_blank_disables_default_fallback(monkeypatch):
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_FALLBACKS", "")

    assert configured_paper_fallback_names("dhan") == ()


def test_short_dhan_period_uses_at_least_seven_calendar_days(monkeypatch):
    class _FixedDateTime:
        @classmethod
        def now(cls, _tz):
            class _Now:
                def date(self):
                    return date(2026, 9, 28)
            return _Now()

    monkeypatch.setattr(dhan_provider, "datetime", _FixedDateTime)
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "paper-client")
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "paper-token")
    monkeypatch.setenv("DHAN_SECURITY_ID_NIFTY", "13")
    monkeypatch.setenv("DHAN_EXCHANGE_SEGMENT_NIFTY", "IDX_I")

    captured = {}

    class _FakeDhan:
        def intraday_minute_data(self, **kwargs):
            captured.update(kwargs)
            return {"data": {"timestamp": [], "open": [], "high": [], "low": [], "close": [], "volume": []}}

    monkeypatch.setattr(dhan_provider, "dhan_sdk_client", lambda: _FakeDhan())

    dhan_provider.DhanProvider().get_candles("NIFTY", "1m", "1d", 200)

    assert captured["to_date"] == "2026-09-28"
    assert captured["from_date"] == "2026-09-21"
