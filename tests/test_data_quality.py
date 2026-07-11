from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from app.validation.data_quality import (
    validate_candles,
    validate_fundamental_snapshot,
    validate_option_chain_rows,
)
from conftest import admin_headers


def test_candle_validation_rejects_invalid_ohlc_shape():
    _valid, report = validate_candles(
        [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "open": 100,
                "high": 99,
                "low": 98,
                "close": 100,
                "volume": 1000,
            }
        ],
        source="broker",
    )

    assert report.status == "FAIL"
    assert report.errors


def test_option_chain_validation_normalizes_provider_aliases():
    valid, report = validate_option_chain_rows(
        [
            {
                "strike": 22500,
                "CE": {"lastPrice": 120, "openInterest": 1000, "impliedVolatility": 18},
                "PE": {"lastPrice": 90, "openInterest": 800, "impliedVolatility": 19},
            }
        ],
        source="broker-option-chain",
    )

    assert report.status == "PASS"
    assert valid[0]["ce"]["oi"] == 1000
    assert valid[0]["pe"]["ltp"] == 90


def test_option_chain_validation_rejects_structural_and_market_integrity_errors():
    _valid, report = validate_option_chain_rows(
        [
            {"strike": 22500, "ce": {"oi": 100, "bid": {"price": 12}, "ask": {"price": 10}}, "pe": {"oi": 90}},
            {"strike": 22500, "ce": {"oi": 110}, "pe": {"oi": 95}},
        ],
        source="broker-option-chain",
        expiry="2020-01-01",
    )

    assert report.status == "FAIL"
    assert any("duplicate strikes" in error for error in report.errors)
    assert any("bid exceeds ask" in error for error in report.errors)
    assert any("expiry is in the past" in error for error in report.errors)


def test_fundamental_validation_marks_missing_data_unavailable():
    report = validate_fundamental_snapshot({"symbol": "MISS", "name": "Missing Data Ltd"}, source="fundamentals")

    assert report.status in {"WARN", "FAIL"}
    assert "revenue_growth_3y" in report.missing_fields
    assert any("unavailable" in warning for warning in report.warnings)


def test_data_quality_dashboard_endpoint_returns_reports(app_client):
    headers = admin_headers(app_client)

    response = app_client.get("/data-quality/dashboard", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "overall_quality_score" in payload
    assert isinstance(payload["reports"], list)
    assert {item["subject"] for item in payload["reports"]} >= {"candles", "provider", "option_chain", "fundamentals"}
