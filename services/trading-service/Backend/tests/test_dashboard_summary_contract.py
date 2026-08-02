from __future__ import annotations

from conftest import admin_headers


def test_dashboard_summary_exposes_only_canonical_five_section_contract(app_client):
    response = app_client.get("/dashboard/summary", headers=admin_headers(app_client))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == {
        "status",
        "contract_version",
        "updated_at",
        "market_decision",
        "why_this_decision",
        "trade_or_no_trade",
        "key_levels",
        "system_trust",
    }
    assert payload["status"] == "ready"
    assert payload["contract_version"] == "1.0"
    assert payload["market_decision"]["decision"] in {"Buy CE", "Buy PE", "No Trade"}
    assert "not probability of profit" in payload["market_decision"]["trade_confidence"]["meaning"]
    eligibility = payload["trade_or_no_trade"]["eligibility"]
    if eligibility["eligible"]:
        assert payload["trade_or_no_trade"]["trade_plan"] is not None
        assert payload["trade_or_no_trade"]["no_trade"] is None
    else:
        assert payload["trade_or_no_trade"]["trade_plan"] is None
        assert payload["trade_or_no_trade"]["no_trade"] is not None
    assert "data_quality" in payload["system_trust"]
    assert "worker" in payload["system_trust"]


def test_product_dashboard_summary_uses_same_contract(app_client):
    response = app_client.get(
        "/product/dashboard-summary",
        headers=admin_headers(app_client),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["contract_version"] == "1.0"
    assert set(payload) == {
        "status",
        "contract_version",
        "updated_at",
        "market_decision",
        "why_this_decision",
        "trade_or_no_trade",
        "key_levels",
        "system_trust",
    }
