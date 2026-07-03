from __future__ import annotations

from Backend.application.institutional_dashboard import build_institutional_dashboard
from conftest import admin_headers


def _option_chain_payload() -> dict:
    return {
        "source": "dhan-option-chain",
        "provider_available": True,
        "pcr": 1.18,
        "max_pain": 24400,
        "updated_at": "2026-07-03T06:30:00+00:00",
        "rows": [
            {
                "strike": 24350,
                "ce": {"oi": 1200, "oi_change": 50},
                "pe": {"oi": 3100, "oi_change": 140},
            },
            {
                "strike": 24400,
                "ce": {"oi": 4200, "oi_change": -80},
                "pe": {"oi": 1800, "oi_change": 30},
            },
        ],
    }


def test_institutional_dashboard_uses_configured_inputs_and_live_option_metrics(monkeypatch):
    monkeypatch.setenv("FII_CASH_FLOW", "150.5")
    monkeypatch.setenv("DII_CASH_FLOW", "-20")
    monkeypatch.setenv("FII_INDEX_FUTURES", "12500")
    monkeypatch.setenv("GIFT_NIFTY", "24510")
    monkeypatch.setenv("INDIA_VIX", "13.4")
    monkeypatch.setenv("USDINR", "83.25")
    monkeypatch.setenv("CRUDE_OIL", "84.7")
    monkeypatch.setenv("GOLD", "2350")
    monkeypatch.setenv("GLOBAL_INDICES_JSON", '[{"label":"S&P 500","value":6200,"change_pct":0.4}]')

    payload = build_institutional_dashboard("NIFTY", option_chain=_option_chain_payload())

    assert payload["module"] == "institutional_dashboard"
    assert payload["cash_flows"]["fii_cash"]["value"] == 150.5
    assert payload["derivatives"]["pcr"] == 1.18
    assert payload["derivatives"]["highest_call_oi"] == {"strike": 24400, "oi": 4200.0}
    assert payload["derivatives"]["highest_put_oi"] == {"strike": 24350, "oi": 3100.0}
    assert payload["derivatives"]["oi_change"] == {"call": -30.0, "put": 170.0, "net": 200.0}
    assert payload["global_indices"][0]["label"] == "S&P 500"
    assert "synthetic" not in payload["data_policy"].lower()


def test_institutional_dashboard_marks_missing_live_option_metrics():
    payload = build_institutional_dashboard(
        "NIFTY",
        option_chain={"source": "option-chain-unavailable", "provider_available": False, "rows": [], "warning": "HTTP 401"},
    )

    assert payload["derivatives"]["pcr"] is None
    assert payload["derivatives"]["max_pain"] is None
    assert payload["derivatives"]["highest_call_oi"] is None
    assert any("Live option-chain metrics are unavailable" in warning for warning in payload["warnings"])


def test_institutional_dashboard_api_contract(app_client, monkeypatch):
    from Backend.presentation.api import institutional_api

    monkeypatch.setattr(institutional_api, "build_institutional_dashboard", lambda symbol, **kwargs: {
        "module": "institutional_dashboard",
        "symbol": symbol,
        "cash_flows": {},
        "futures": {},
        "derivatives": {},
        "macro": {},
        "global_indices": [],
        "market_narrative": "ok",
        "warnings": [],
    })

    response = app_client.get("/institutional/dashboard?symbol=NIFTY", headers=admin_headers(app_client))

    assert response.status_code == 200, response.text
    assert response.json()["module"] == "institutional_dashboard"
