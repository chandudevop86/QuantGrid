def test_manual_option_endpoint_forwards_authenticated_request(app_client, admin_headers, monkeypatch):
    from Backend.presentation.api import market_api
    from Backend.application.options import auto_paper_execution

    monkeypatch.setattr(market_api, "kill_switch_status", lambda **kwargs: {"active": False})
    calls = []

    def record(**kwargs):
        calls.append(kwargs)
        return {"status": "paper_simulated", "option_order_id": 7, "broker_submitted": False}

    monkeypatch.setattr(auto_paper_execution, "submit_manual_option_paper", record)
    response = app_client.post("/market/option-buyer/paper-order", headers=admin_headers, json={
        "symbol": "NIFTY", "side": "PE", "strike": 25000, "lots": 1,
        "execution_mode": "paper", "idempotency_key": "manual-api-request-0001",
    })
    assert response.status_code == 200
    assert response.json()["option_order_id"] == 7
    assert calls[0]["actor_id"] == "user:1"
    assert calls[0]["side"] == "PE"
    assert calls[0]["lots"] == 1


def test_expiry_resolution_requires_operator_and_confirmation(app_client, admin_headers, monkeypatch):
    from Backend.core.database import SessionLocal
    from Backend.domain.security.models import User
    from Backend.domain.security.passwords import hash_password
    from Backend.application.options import auto_paper_execution

    with SessionLocal() as database:
        database.add(User(username="expiry-trader", password_hash=hash_password("TraderPass1!"), role="trader"))
        database.commit()
    login = app_client.post("/auth/login", json={"username": "expiry-trader", "password": "TraderPass1!"})
    assert login.status_code == 200
    trader_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    calls = []

    def settle(identity, **kwargs):
        calls.append((identity, kwargs))
        return {"id": identity, "status": "closed", "exit_price": 0}

    monkeypatch.setattr(auto_paper_execution, "settle_expired_option_paper", settle)
    payload = {"final_underlying_price": 24900, "evidence_reference": "Reviewed exchange settlement record",
               "confirmed_final_settlement": True}
    url = "/market/option-buyer/paper-positions/1/settle"
    assert app_client.post(url, headers=trader_headers, json=payload).status_code == 403
    assert calls == []
    assert app_client.post(url, headers=admin_headers, json={**payload, "confirmed_final_settlement": False}).status_code == 422
    assert calls == []
    approved = app_client.post(url, headers=admin_headers, json=payload)
    assert approved.status_code == 200
    assert calls[0][1]["actor_id"] == "user:1"
    assert approved.json()["settlement_source"] == "manual_final_settlement"
