from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from Backend.application import quality_growth_screener as screen


TODAY = date(2026, 10, 19)


def good_stock(**changes):
    item = {
        "symbol": "QGTEST",
        "name": "Sample Test Company (not a live stock)",
        "sector": "Industrials",
        "market_segment": "MAINBOARD",
        "market_cap_cr": 4500,
        "roe": 24,
        "roce": 31,
        "debt_to_equity": 0.15,
        "sales_growth_3y": 22,
        "profit_growth_3y": 21,
        "opm": 21,
        "pledged_percentage": 0,
        "cash_from_operations_cr": 30,
        "pe": 24,
        "current_price": 200,
        "dma200": 150,
        "dma50": 175,
        "avg_daily_volume_1m": 35000,
        "fundamentals_as_of": "2026-09-30",
        "price_as_of": "2026-10-19",
    }
    item.update(changes)
    return item


def data_feed(**changes):
    payload = {"source": "test-fixture-not-live", "as_of": "2026-10-19", "stocks": [good_stock()]}
    payload.update(changes)
    return payload


def test_quality_growth_high_quality_company_is_research_not_order():
    result = screen.evaluate_stock(good_stock(), today=TODAY)
    assert result["status"] == "QUALIFIED"
    assert 0 <= result["score"] <= 100
    assert set(result["component_scores"]) == {"quality", "growth", "valuation", "momentum", "risk"}
    assert sum(result["component_scores"].values()) == pytest.approx(result["score"])
    snapshot = screen.build_screen_snapshot(
        data_feed(), now=datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    )
    assert snapshot["status"] == "READY"
    assert snapshot["qualified_count"] == 1
    assert snapshot["execution_enabled"] is False
    assert "not a trade" in snapshot["disclaimer"]


@pytest.mark.parametrize("field,value", [
    ("market_cap_cr", 300),
    ("roe", 15),
    ("roce", 18),
    ("debt_to_equity", 0.5),
    ("sales_growth_3y", 12),
    ("profit_growth_3y", 12),
    ("opm", 12),
    ("pledged_percentage", 5),
    ("cash_from_operations_cr", 0),
    ("pe", 60),
    ("current_price", 149),
    ("avg_daily_volume_1m", 100),
])
def test_screener_v2_thresholds_fail_closed(field, value):
    result = screen.evaluate_stock(good_stock(**{field: value}), today=TODAY)
    assert result["status"] == "REJECTED"
    assert result["score"] is None
    assert result["reasons"]


@pytest.mark.parametrize("changes", [
    {"pe": None},
    {"roe": float("nan")},
    {"profit_growth_3y": float("inf")},
    {"market_cap_cr": True},
    {"fundamentals_as_of": "2025-01-01"},
    {"fundamentals_as_of": "2026-10-20"},
    {"price_as_of": "2026-10-10"},
    {"price_as_of": "2026-10-21"},
    {"market_segment": "UNKNOWN"},
    {"sector": "Banking"},
    {"sector": "Financial Services"},
])
def test_missing_stale_or_incompatible_data_is_unverified(changes):
    result = screen.evaluate_stock(good_stock(**changes), today=TODAY)
    assert result["status"] == "UNVERIFIED"
    assert result["score"] is None


def test_invalid_50dma_does_not_score_as_valid_momentum():
    stock = screen.evaluate_stock(good_stock(dma50=-1), today=TODAY)
    assert stock["status"] == "UNVERIFIED"
    assert stock["score"] is None


def test_sme_requires_manual_review_even_when_financials_pass():
    stock = screen.evaluate_stock(good_stock(market_segment="SME"), today=TODAY)
    assert stock["status"] == "QUALIFIED"
    assert stock["market_cap_bucket"] == "SME"
    assert stock["research_priority"] == "MANUAL_REVIEW"
    assert any("SME" in note for note in stock["reasons"])


def test_missing_dma50_is_not_optimistically_filled():
    verified = screen.evaluate_stock(good_stock(), today=TODAY)
    partial = screen.evaluate_stock(good_stock(dma50=None), today=TODAY)
    assert partial["status"] == "QUALIFIED"
    assert partial["component_scores"]["momentum"] < verified["component_scores"]["momentum"]
    assert "50-day average" in partial["reasons"][0]


def test_snapshot_rejects_duplicate_or_stale_universe():
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Duplicate"):
        screen.build_screen_snapshot(data_feed(stocks=[good_stock(), good_stock()]), now=now)
    with pytest.raises(ValueError, match="stale"):
        screen.build_screen_snapshot(data_feed(as_of="2026-10-01"), now=now)
    with pytest.raises(ValueError, match="future"):
        screen.build_screen_snapshot(data_feed(as_of="2026-10-20"), now=now)
    with pytest.raises(ValueError, match="timezone-aware"):
        screen.build_screen_snapshot(data_feed(), now=datetime(2026, 10, 19))


def test_refresh_local_file_changed_and_no_synthetic_fallback(tmp_path, monkeypatch):
    file = tmp_path / "licensed-stock-feed.json"
    file.write_text(json.dumps(data_feed()), encoding="utf-8")
    monkeypatch.setenv("QUANTGRID_QUALITY_GROWTH_FEED_PATH", str(file))
    monkeypatch.delenv("QUANTGRID_QUALITY_GROWTH_FEED_URL", raising=False)
    screen._CACHE.clear()
    monkeypatch.setattr(screen, "build_screen_snapshot", lambda payload: {"status": "READY", "source": payload["source"], "execution_enabled": False})
    first = screen.latest_quality_growth_screen()
    assert first["status"] == "READY"
    file.write_text("invalid json", encoding="utf-8")
    # Repeated page requests use cached validated data until TTL expires.
    assert screen.latest_quality_growth_screen()["status"] == "READY"
    assert screen.latest_quality_growth_screen(force=True)["status"] == "UNAVAILABLE"
    assert screen.latest_quality_growth_screen(force=True)["items"] == []
    screen._CACHE.clear()


def test_empty_feed_configuration_is_unavailable_not_demo(monkeypatch):
    monkeypatch.delenv("QUANTGRID_QUALITY_GROWTH_FEED_PATH", raising=False)
    monkeypatch.delenv("QUANTGRID_QUALITY_GROWTH_FEED_URL", raising=False)
    payload = screen.latest_quality_growth_screen()
    assert payload["status"] == "UNCONFIGURED"
    assert payload["items"] == []
    assert not payload["execution_enabled"]


def test_https_feed_needs_explicit_host_and_rejects_local_ip(monkeypatch):
    monkeypatch.delenv("QUANTGRID_QUALITY_GROWTH_FEED_PATH", raising=False)
    monkeypatch.setenv("QUANTGRID_QUALITY_GROWTH_FEED_URL", "https://127.0.0.1/data.json")
    monkeypatch.setenv("QUANTGRID_QUALITY_GROWTH_ALLOWED_HOST", "127.0.0.1")
    assert screen.latest_quality_growth_screen()["status"] == "UNCONFIGURED"
    monkeypatch.setenv("QUANTGRID_QUALITY_GROWTH_ALLOWED_HOST", "trusted.example.com")
    assert screen.latest_quality_growth_screen()["status"] == "UNCONFIGURED"


def test_quality_growth_endpoint_requires_auth_and_does_not_trade(app_client, monkeypatch):
    from Backend.presentation.api import investing_api
    from conftest import make_admin_headers

    monkeypatch.setattr(investing_api, "latest_quality_growth_screen", lambda: {
        "status": "UNCONFIGURED", "items": [], "excluded": [],
        "qualified_count": 0, "execution_enabled": False,
    })
    assert app_client.get("/investing/stocks/quality-growth").status_code in {401, 403}
    response = app_client.get(
        "/investing/stocks/quality-growth", headers=make_admin_headers(app_client)
    )
    assert response.status_code == 200
    assert response.json()["execution_enabled"] is False
    assert response.json()["items"] == []
