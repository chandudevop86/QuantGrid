from __future__ import annotations

from conftest import admin_headers


def test_quant_modules_dashboard_exposes_four_modules(app_client):
    headers = admin_headers(app_client)

    response = app_client.get("/modules/dashboard", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"option_chain", "backtesting", "risk_engine", "trade_journal"}
    assert payload["option_chain"]["source"] == "synthetic-demo-chain"
    assert "pcr" in payload["option_chain"]
    assert "max_pain" in payload["option_chain"]
    assert "equity_curve" in payload["backtesting"]
    assert payload["risk_engine"]["state"] in {"normal", "halted"}
    assert "win_rate" in payload["trade_journal"]


def test_backtesting_module_accepts_payload(app_client):
    headers = admin_headers(app_client)
    candles = [
        {"timestamp": "2026-05-22T09:15:00+05:30", "open": 100, "high": 104, "low": 99, "close": 102, "volume": 1000},
        {"timestamp": "2026-05-22T09:20:00+05:30", "open": 102, "high": 106, "low": 101, "close": 105, "volume": 1000},
        {"timestamp": "2026-05-22T09:25:00+05:30", "open": 105, "high": 107, "low": 103, "close": 104, "volume": 1000},
    ]

    response = app_client.post(
        "/modules/backtesting",
        json={"symbol": "NIFTY", "strategy_name": "amd", "candles": candles, "min_score": 0},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["module"] == "backtesting"
    assert payload["payload"]["candles"] == len(candles)
    assert "recent_outcomes" in payload
    assert {"cagr", "profit_factor", "average_profit", "average_loss", "win_rate_pct"} <= set(payload["metrics"])


def test_backtesting_comparison_ranks_strategy_runs(app_client):
    headers = admin_headers(app_client)
    candles = [
        {"timestamp": "2026-05-22T09:15:00+05:30", "open": 100, "high": 104, "low": 99, "close": 102, "volume": 1000},
        {"timestamp": "2026-05-22T09:20:00+05:30", "open": 102, "high": 108, "low": 101, "close": 107, "volume": 1100},
        {"timestamp": "2026-05-22T09:25:00+05:30", "open": 107, "high": 111, "low": 105, "close": 110, "volume": 1200},
        {"timestamp": "2026-05-22T09:30:00+05:30", "open": 110, "high": 113, "low": 108, "close": 111, "volume": 1300},
        {"timestamp": "2026-05-22T09:35:00+05:30", "open": 111, "high": 116, "low": 110, "close": 115, "volume": 1400},
    ]

    response = app_client.post(
        "/modules/backtesting/comparison",
        json={"symbol": "NIFTY", "strategies": ["amd", "breakout"], "candles": candles, "min_score": 0},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["module"] == "backtesting_comparison"
    assert len(payload["runs"]) == 2
    assert len(payload["ranked"]) == 2
    assert payload["best_strategy"] in {"amd", "breakout"}
    assert "equity_curve" in payload["runs"][0]


def test_historical_option_chain_module_returns_snapshots(app_client):
    headers = admin_headers(app_client)

    response = app_client.get("/modules/option-chain/NIFTY/historical", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["module"] == "historical_option_chain"
    assert payload["source"] == "synthetic-historical-chain"
    assert len(payload["snapshots"]) == 12
    assert {"timestamp", "underlying_price", "atm_strike", "pcr", "max_pain"} <= set(payload["snapshots"][0])


def test_live_nse_option_chain_returns_real_chain_payload(app_client, monkeypatch):
    import Backend.presentation.api.modules_api as modules_api

    monkeypatch.setattr(
        modules_api,
        "live_nse_option_chain",
        lambda *args, **kwargs: {
            "module": "live_nse_option_chain",
            "symbol": "NIFTY",
            "source": "live-nse-chain",
            "underlying_price": 22500,
            "atm_strike": 22500,
            "expiry": "27-Jun-2026",
            "pcr": 1.12,
            "max_pain": 22500,
            "signals": {"bias": "BULLISH", "total_call_oi": 1000, "total_put_oi": 1120},
            "rows": [{"strike": 22500, "ce": {"oi": 1000}, "pe": {"oi": 1120}}],
        },
    )
    headers = admin_headers(app_client)

    response = app_client.get("/modules/option-chain/NIFTY/live-nse", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "live-nse-chain"
    assert payload["pcr"] == 1.12
    assert payload["signals"]["bias"] == "BULLISH"
    assert payload["rows"][0]["ce"]["oi"] == 1000


def test_live_nse_option_chain_falls_back_when_nse_is_unavailable(app_client, monkeypatch):
    import Backend.presentation.api.modules_api as modules_api

    monkeypatch.setattr(
        modules_api,
        "live_nse_option_chain",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("NSE blocked request")),
    )
    headers = admin_headers(app_client)

    response = app_client.get("/modules/option-chain/NIFTY/live-nse", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["module"] == "live_nse_option_chain"
    assert payload["source"] == "synthetic-demo-chain"
    assert payload["underlying_price"] > 0
    assert payload["pcr"] is not None
    assert payload["fallback_reason"] == "RuntimeError"
    assert payload["provider_warning"] == "Live NSE option-chain provider unavailable; using synthetic fallback data."
    assert "NSE blocked request" in payload["fallback_detail"]


def test_live_nse_option_chain_function_falls_back_on_http_403(monkeypatch):
    from urllib.error import HTTPError

    import Backend.application.quant_modules as quant_modules

    class BlockedOpener:
        def open(self, *args, **kwargs):
            raise HTTPError("https://www.nseindia.com", 403, "Forbidden", None, None)

    monkeypatch.setattr(quant_modules, "build_opener", lambda *args, **kwargs: BlockedOpener())
    monkeypatch.setattr(quant_modules, "latest_price_tick", lambda symbol: {"price": 22500})

    payload = quant_modules.live_nse_option_chain("NIFTY")

    assert payload["module"] == "live_nse_option_chain"
    assert payload["source"] == "synthetic-demo-chain"
    assert payload["fallback_reason"] == "HTTPError"
    assert payload["provider_warning"] == "Live NSE option-chain provider unavailable; using synthetic fallback data."
    assert "HTTP Error 403" in payload["fallback_detail"]
