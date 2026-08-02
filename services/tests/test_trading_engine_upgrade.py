from __future__ import annotations

from conftest import admin_headers


def _basket_payload(**overrides):
    leg = {
        "strategy": "manual_basket",
        "symbol": "NIFTY",
        "side": "BUY",
        "quantity": 2,
        "entry": 100.0,
        "stop_loss": 95.0,
        "target": 110.0,
        "trailing_stop_pct": 1.0,
    }
    leg.update(overrides.pop("leg", {}))
    return {"execution_mode": "paper", "reason": "test basket", "legs": [leg], **overrides}


def test_trading_engine_dashboard_exposes_phase5_capabilities(app_client):
    headers = admin_headers(app_client)

    response = app_client.get("/execution/trading-engine/dashboard", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["module"] == "trading_engine"
    assert payload["capabilities"]["stop_loss"] is True
    assert payload["capabilities"]["trailing_stop_loss"] is True
    assert payload["capabilities"]["target"] is True
    assert payload["capabilities"]["scale_in"] == "paper"
    assert payload["capabilities"]["scale_out"] == "paper"
    assert payload["capabilities"]["basket_orders"] == "paper"
    assert payload["capabilities"]["paper_execution_logs"] is True
    assert payload["capabilities"]["kill_switch"] is True
    assert payload["capabilities"]["audit_trail"] is True
    assert payload["guardrails"]["paper_only_new_workflows"] is True


def test_paper_basket_creates_trade_and_open_position(app_client):
    headers = admin_headers(app_client)

    response = app_client.post("/execution/trading-engine/basket", json=_basket_payload(), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "paper_basket_submitted"
    assert payload["created_count"] == 1
    position = payload["legs"][0]["position"]
    assert position["symbol"] == "NIFTY"
    assert position["quantity"] == 2
    assert position["stop_loss"] == 95.0
    assert position["target"] == 110.0
    assert position["trailing_stop_pct"] == 1.0

    dashboard = app_client.get("/execution/trading-engine/dashboard", headers=headers).json()
    assert dashboard["summary"]["open_positions"] == 1
    assert dashboard["paper_execution_logs"][0]["status"] == "paper_basket_submitted"


def test_basket_rejects_live_mode(app_client):
    headers = admin_headers(app_client)

    response = app_client.post(
        "/execution/trading-engine/basket",
        json=_basket_payload(execution_mode="live"),
        headers=headers,
    )

    assert response.status_code == 400
    assert "paper-only" in response.json()["detail"]


def test_scale_out_updates_position_and_writes_paper_log(app_client):
    headers = admin_headers(app_client)
    created = app_client.post("/execution/trading-engine/basket", json=_basket_payload(), headers=headers).json()
    position_id = created["legs"][0]["position"]["id"]

    response = app_client.post(
        f"/execution/trading-engine/positions/{position_id}/scale",
        json={"execution_mode": "paper", "action": "scale_out", "quantity": 1, "price": 104.0},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "scale_out"
    assert payload["old_quantity"] == 2
    assert payload["new_quantity"] == 1
    assert payload["realized_pnl"] == 4.0
    assert payload["paper_log"]["status"] == "scale_out"

    dashboard = app_client.get("/execution/trading-engine/dashboard", headers=headers).json()
    assert dashboard["open_positions"][0]["quantity"] == 1
