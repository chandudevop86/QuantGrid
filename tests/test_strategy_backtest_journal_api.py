from __future__ import annotations

from conftest import admin_headers


def test_strategy_registry_exposes_required_strategies(app_client):
    headers = admin_headers(app_client)

    response = app_client.get("/trading/strategies", headers=headers)

    assert response.status_code == 200
    assert {
        "breakout",
        "mean_reversion",
        "supply_demand",
        "mtf",
        "btst",
        "cbt",
        "crt_tbs",
        "mtfa",
    }.issubset(set(response.json()))


def test_strategy_backtest_api_returns_card_metrics(app_client):
    headers = admin_headers(app_client)

    response = app_client.get("/api/strategies/breakout/backtest", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["input"]["strategy"] == "breakout"
    assert payload["metrics"]["total_trades"] > 0
    assert {"total_trades", "win_rate", "pnl", "max_drawdown", "sharpe_ratio", "expectancy"} <= set(payload["metrics"])
    assert payload["metrics"]["recent_accuracy"] == payload["metrics"]["win_rate"]


def test_trade_journal_api_creates_and_lists_entries(app_client):
    headers = admin_headers(app_client)

    created = app_client.post(
        "/api/trade-journal",
        headers=headers,
        json={
            "strategy": "breakout",
            "signal": "BUY",
            "symbol": "NIFTY",
            "entry": 22500,
            "stop_loss": 22450,
            "target": 22600,
            "quantity": 50,
            "status": "accepted_signal",
            "reason": "setup valid",
            "source": "test",
            "exit_price": 22600,
            "pnl": 100,
            "exit_reason": "target",
        },
    )
    listed = app_client.get("/api/trade-journal", headers=headers)

    assert created.status_code == 200
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["summary"]["total_trades"] == 1
    assert payload["rows"][0]["strategy"] == "breakout"
    assert payload["rows"][0]["exit_reason"] == "target"
    assert payload["rows"][0]["entry_price"] == 22500
    assert payload["rows"][0]["quantity"] == 50


def test_trade_journal_crud_and_filters(app_client):
    headers = admin_headers(app_client)

    created = app_client.post(
        "/api/trades/journal",
        headers=headers,
        json={
            "strategy": "mtf",
            "signal": "SELL",
            "symbol": "BANKNIFTY",
            "status": "rejected_signal",
            "entry_price": 50000,
            "stop_loss": 50100,
            "target": 49800,
            "quantity": 15,
            "reason": "risk rejected",
            "source": "signal_scan",
        },
    )
    assert created.status_code == 200, created.text
    entry_id = created.json()["id"]

    fetched = app_client.get(f"/api/trades/journal/{entry_id}", headers=headers)
    patched = app_client.patch(
        f"/api/trades/journal/{entry_id}",
        headers=headers,
        json={"status": "closed", "exit_price": 49800, "pnl": 200, "exit_reason": "target"},
    )
    filtered = app_client.get("/api/trades/journal", headers=headers, params={"strategy": "mtf", "status": "closed", "symbol": "BANKNIFTY"})

    assert fetched.status_code == 200
    assert patched.status_code == 200
    assert patched.json()["status"] == "closed"
    assert patched.json()["exit_reason"] == "target"
    assert filtered.status_code == 200
    assert filtered.json()["summary"]["total_trades"] == 1


def test_trade_journal_unprefixed_aliases_match_proxy_rewrite_contract(app_client):
    headers = admin_headers(app_client)

    created = app_client.post(
        "/trades/journal",
        headers=headers,
        json={
            "strategy": "breakout",
            "signal": "BUY",
            "symbol": "NIFTY",
            "entry_price": 22500,
            "stop_loss": 22450,
            "target": 22600,
            "quantity": 50,
            "status": "accepted_signal",
            "source": "proxy-contract-test",
        },
    )

    assert created.status_code == 200, created.text
    entry_id = created.json()["id"]

    listed = app_client.get("/trades/journal", headers=headers)
    fetched = app_client.get(f"/trades/journal/{entry_id}", headers=headers)
    patched = app_client.patch(f"/trades/journal/{entry_id}", headers=headers, json={"status": "closed", "exit_reason": "manual"})

    assert listed.status_code == 200
    assert fetched.status_code == 200
    assert patched.status_code == 200
    assert patched.json()["status"] == "closed"


def test_live_nse_option_chain_fallback_exposes_frontend_fields(app_client, monkeypatch):
    import Backend.presentation.api.modules_api as modules_api

    monkeypatch.setattr(
        modules_api,
        "live_nse_option_chain",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )
    headers = admin_headers(app_client)

    response = app_client.get("/modules/option-chain/NIFTY/live-nse", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "synthetic"
    assert {"underlying", "spot", "expiry", "ATM", "atm", "pcr", "max_pain", "support", "resistance", "signal"} <= set(payload)
    assert payload["synthetic"] is True


def test_synthetic_option_chain_response_contract(app_client):
    headers = admin_headers(app_client)

    response = app_client.get("/modules/option-chain/NIFTY", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["underlying"] == "NIFTY"
    assert payload["source"] == "synthetic"
    assert payload["signal"] in {"BUY_CE", "BUY_PE", "NO_TRADE"}


def test_signals_alias_reuses_latest_handler(app_client):
    headers = admin_headers(app_client)

    response = app_client.get("/api/signals", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert {"active_signals", "rejected_signals", "stale_signals", "symbol"} <= set(payload)
