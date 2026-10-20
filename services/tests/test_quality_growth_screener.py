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


def valid_sme(**changes):
    data = good_stock(
        market_segment="SME",
        traded_sessions_20=19,
        median_bid_ask_spread_pct=0.8,
        exchange_lot_size=1000,
        circuit_hit_sessions_20=1,
        circuit_limit_pct=5,
        promoter_holding_pct=62,
        promoter_disclosure_as_of="2026-09-30",
        sme_microstructure_as_of="2026-10-19",
    )
    data.update(changes)
    return data


def financial_stock(kind, **changes):
    stock = {
        "symbol": "QGBANK" if kind == "BANK" else "QGNBFC",
        "name": "Synthetic Finance Test (not a live stock)",
        "sector": "Banking" if kind == "BANK" else "NBFC",
        "financial_type": kind,
        "market_segment": "MAINBOARD",
        "market_cap_cr": 25000,
        "roe": 19,
        "roa_pct": 1.8,
        "capital_adequacy_pct": 19,
        "net_profit_growth_3y_pct": 18,
        "nim_pct": 3.6,
        "price_to_book": 2.2,
        "pledged_percentage": 0,
        "current_price": 200,
        "dma200": 160,
        "dma50": 180,
        "avg_daily_volume_1m": 50000,
        "fundamentals_as_of": "2026-09-30",
        "price_as_of": "2026-10-19",
    }
    if kind == "BANK":
        stock.update(gross_npa_pct=2, net_npa_pct=0.7, credit_growth_3y_pct=19)
    else:
        stock.update(gross_stage3_pct=2, net_stage3_pct=0.7, loan_book_growth_3y_pct=19)
    stock.update(changes)
    return stock


def test_sme_missing_risk_fields_are_unverified():
    stock = screen.evaluate_stock(good_stock(market_segment="SME"), today=TODAY)
    assert stock["status"] == "UNVERIFIED"
    assert stock["score"] is None
    assert "traded_sessions_20" in stock["reasons"][0]


def test_sme_requires_manual_review_even_after_verification():
    stock = screen.evaluate_stock(valid_sme(), today=TODAY)
    assert stock["status"] == "QUALIFIED"
    assert stock["market_cap_bucket"] == "SME"
    assert stock["research_priority"] == "MANUAL_REVIEW"
    assert stock["sme_checks"]["exchange_lot_size"] == 1000
    assert any("SME" in note for note in stock["reasons"])


@pytest.mark.parametrize("changes, expected", [
    ({"traded_sessions_20": 12}, "REJECTED"),
    ({"median_bid_ask_spread_pct": 2.4}, "REJECTED"),
    ({"circuit_hit_sessions_20": 5}, "REJECTED"),
    ({"exchange_lot_size": None}, "UNVERIFIED"),
    ({"exchange_lot_size": 1.5}, "UNVERIFIED"),
    ({"promoter_disclosure_as_of": "2026-01-01"}, "UNVERIFIED"),
    ({"sme_microstructure_as_of": None}, "UNVERIFIED"),
    ({"sme_microstructure_as_of": "2026-10-09"}, "UNVERIFIED"),
    ({"circuit_limit_pct": 0}, "UNVERIFIED"),
])
def test_sme_risk_checks_fail_closed(changes, expected):
    stock = screen.evaluate_stock(valid_sme(**changes), today=TODAY)
    assert stock["status"] == expected
    assert stock["score"] is None


@pytest.mark.parametrize("kind", ["BANK", "NBFC"])
def test_financials_have_separate_score_without_corporate_ratios(kind):
    stock = screen.evaluate_stock(financial_stock(kind), today=TODAY)
    assert stock["status"] == "QUALIFIED"
    assert stock["screen_type"] == kind
    assert stock["component_scores"]["quality"] > 0
    assert stock["financial_metrics"]["roa_pct"] == 1.8
    assert stock["financial_metrics"]["capital_adequacy_pct"] == 19
    assert stock["research_priority"] != "HIGH" or stock["score"] >= 80
    assert all("ROCE" not in msg and "OPM" not in msg for msg in stock["reasons"])


@pytest.mark.parametrize("kind, changes", [
    ("BANK", {"gross_npa_pct": None}),
    ("BANK", {"capital_adequacy_pct": 8}),
    ("BANK", {"net_npa_pct": 4}),
    ("NBFC", {"gross_stage3_pct": None}),
    ("NBFC", {"capital_adequacy_pct": 9}),
    ("NBFC", {"loan_book_growth_3y_pct": 3}),
])
def test_financials_dont_pass_with_missing_or_weak_ratios(kind, changes):
    stock = screen.evaluate_stock(financial_stock(kind, **changes), today=TODAY)
    assert stock["status"] in {"UNVERIFIED", "REJECTED"}
    assert stock["score"] is None


def test_explicit_financial_type_required_and_must_match_sector():
    missing = screen.evaluate_stock(good_stock(sector="Banking"), today=TODAY)
    assert missing["status"] == "UNVERIFIED"
    assert missing["screen_type"] == "FINANCIAL_UNCLASSIFIED"
    mismatch = screen.evaluate_stock(financial_stock("BANK", sector="Industrials"), today=TODAY)
    assert mismatch["status"] == "UNVERIFIED"
    unsupported = screen.evaluate_stock(good_stock(financial_type="INSURANCE"), today=TODAY)
    assert unsupported["status"] == "UNVERIFIED"


def test_mixed_screen_sorts_and_retains_excluded_financial_and_sme_details():
    payload = data_feed(stocks=[
        good_stock(),
        financial_stock("BANK"),
        financial_stock("NBFC"),
        valid_sme(symbol="QGSME", circuit_hit_sessions_20=5),
    ])
    snapshot = screen.build_screen_snapshot(
        payload, now=datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    )
    assert snapshot["qualified_count"] == 3
    assert {item["screen_type"] for item in snapshot["items"]} == {"NON_FINANCIAL", "BANK", "NBFC"}
    assert snapshot["execution_enabled"] is False
    assert snapshot["excluded"][0]["market_cap_bucket"] == "SME"
    assert snapshot["excluded"][0]["status"] == "REJECTED"


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
