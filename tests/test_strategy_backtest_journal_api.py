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
    assert payload["source"] == "synthetic-demo-chain"
    assert {"spot", "expiry", "ATM", "pcr", "max_pain", "support", "resistance"} <= set(payload)
