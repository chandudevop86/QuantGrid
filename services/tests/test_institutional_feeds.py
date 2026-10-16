from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from Backend.application import institutional_feeds as feeds
from Backend.application.institutional_dashboard import build_institutional_dashboard


TODAY = date(2026, 10, 16)


def _cash(date_text="16-Oct-2026"):
    return [
        {"category": "FII/FPI", "date": date_text, "buyValue": "1,200.00", "sellValue": "1,250.00", "netValue": "-50.00"},
        {"category": "DII", "date": date_text, "buyValue": "2,000", "sellValue": "1,800", "netValue": "200.00"},
    ]


def _csv():
    return (
        "Participant wise Open Interest\n"
        "Client Type,Future Index Long,Future Index Short,Future Stock Long\n"
        "Client,100,150,20\n"
        'FII,"1,200","1,600",200\n'
        "DII,300,400,500\n"
    )


def test_cash_parses_date_values_and_source():
    result = feeds.parse_cash_activity(_cash(), today=TODAY)
    assert result["fii_cash"]["value"] == -50
    assert result["dii_cash"]["value"] == 200
    assert result["fii_cash"]["as_of"] == "2026-10-16"
    assert result["fii_cash"]["source"] == "nse-eod"


def test_cash_rejects_missing_stale_and_mismatched_dates():
    assert feeds.parse_cash_activity(_cash("09-Oct-2026"), today=TODAY) == {}
    mixed = _cash()
    mixed[1]["date"] = "15-Oct-2026"
    with pytest.raises(ValueError, match="different"):
        feeds.parse_cash_activity(mixed, today=TODAY)
    bad = _cash()
    bad[0]["netValue"] = "nan"
    assert "fii_cash" not in feeds.parse_cash_activity(bad, today=TODAY)


def test_participant_fii_net_and_long_pct():
    result = feeds.parse_participant_oi(_csv(), report_date=TODAY, today=TODAY)
    assert result["fii_index_long"]["value"] == 1200
    assert result["fii_index_short"]["value"] == 1600
    assert result["fii_index_futures"]["value"] == -400
    assert result["fii_index_long_pct"]["value"] == 42.86
    assert result["fii_index_futures"]["scope"] == "all_index_futures"


def test_participant_rejects_missing_fii_and_stale_report():
    with pytest.raises(ValueError, match="no FII"):
        feeds.parse_participant_oi("Client Type,Future Index Long,Future Index Short\nDII,1,2\n", report_date=TODAY, today=TODAY)
    with pytest.raises(ValueError, match="stale"):
        feeds.parse_participant_oi(_csv(), report_date=date(2026, 10, 9), today=TODAY)


def test_live_loader_uses_both_reports_with_source_dates(monkeypatch):
    def fake_fetch(url: str) -> str:
        if url == feeds.CASH_URL:
            return json.dumps(_cash())
        if "fao_participant_oi_16102026.csv" in url:
            return _csv()
        raise OSError("file not found")

    monkeypatch.setattr(feeds, "_fetch_text", fake_fetch)
    result = feeds.fetch_institutional_eod(today=TODAY)
    assert result["warnings"] == []
    assert result["cash_flows"]["fii_cash"]["value"] == -50
    assert result["futures"]["fii_index_futures"]["value"] == -400


def test_loader_blocks_network_failure_and_invalid_cash(monkeypatch):
    monkeypatch.setattr(feeds, "_fetch_text", lambda url: "<html>blocked</html>")
    result = feeds.fetch_institutional_eod(today=TODAY)
    assert result["cash_flows"] == {}
    assert result["futures"] == {}
    assert len(result["warnings"]) == 2


def test_loader_cache_opt_in_and_negative_cache(monkeypatch):
    feeds._CACHE.clear()
    calls = []

    def fake_loader():
        calls.append(1)
        return {"cash_flows": {}, "futures": {}, "warnings": ["not ready"], "checked_at": "now"}

    monkeypatch.setattr(feeds, "fetch_institutional_eod", fake_loader)
    monkeypatch.delenv("QUANTGRID_INSTITUTIONAL_AUTO_FETCH", raising=False)
    assert feeds.get_institutional_eod()["checked_at"] is None
    assert calls == []
    monkeypatch.setenv("QUANTGRID_INSTITUTIONAL_AUTO_FETCH", "true")
    assert feeds.get_institutional_eod()["warnings"] == ["not ready"]
    assert feeds.get_institutional_eod()["warnings"] == ["not ready"]
    assert len(calls) == 1
    feeds._CACHE.clear()


def test_dashboard_merges_published_eod_without_stamping_as_live(monkeypatch):
    for name in ("FII_CASH_FLOW", "DII_CASH_FLOW", "FII_INDEX_FUTURES"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv("QUANTGRID_" + name, raising=False)
    published = {
        "cash_flows": feeds.parse_cash_activity(_cash(), today=TODAY),
        "futures": feeds.parse_participant_oi(_csv(), report_date=TODAY, today=TODAY),
        "warnings": [],
        "checked_at": "2026-10-16T11:00:00+00:00",
    }
    payload = build_institutional_dashboard("NIFTY", institutional_eod=published)
    assert payload["cash_flows"]["fii_cash"]["source"] == "nse-eod"
    assert payload["futures"]["fii_index_futures"]["value"] == -400
    assert payload["futures"]["fii_index_long_pct"]["value"] == 42.86
    assert payload["futures"]["fii_index_futures"]["scope"] == "all_index_futures"


def test_futures_basis_requires_a_fresh_timestamp(monkeypatch):
    for suffix in ("FUTURES_PRICE", "SPOT_PRICE", "FUTURES_AS_OF"):
        monkeypatch.delenv("QUANTGRID_NIFTY_" + suffix, raising=False)
    assert build_institutional_dashboard("NIFTY")["futures"]["basis"]["value"] is None
    monkeypatch.setenv("QUANTGRID_NIFTY_FUTURES_PRICE", "23113")
    monkeypatch.setenv("QUANTGRID_NIFTY_SPOT_PRICE", "23146.15")
    monkeypatch.setenv("QUANTGRID_NIFTY_FUTURES_AS_OF", (datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
    assert build_institutional_dashboard("NIFTY")["futures"]["basis"]["value"] is None
    monkeypatch.setenv("QUANTGRID_NIFTY_FUTURES_AS_OF", datetime.now(timezone.utc).isoformat())
    basis = build_institutional_dashboard("NIFTY")["futures"]["basis"]
    assert basis["value"] == -33.15
    assert basis["premium_pct"] < 0
