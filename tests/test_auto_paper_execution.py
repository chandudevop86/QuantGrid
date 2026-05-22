from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from conftest import admin_headers

from Backend.domain.models.signal import StrategySignal


def _candles() -> list[dict]:
    return [
        {"timestamp": "2026-05-22T15:28:00+05:30", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
        {"timestamp": "2026-05-22T15:29:00+05:30", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 1000},
        {"timestamp": "2026-05-22T15:30:00+05:30", "open": 102, "high": 104, "low": 101, "close": 103, "volume": 1000},
    ]


def _market_response(interval: str = "1m") -> dict:
    return {
        "symbol": "NIFTY",
        "market_symbol": "^NSEI",
        "interval": interval,
        "period": "1d",
        "source": "yahoo-finance",
        "volume_status": "reported",
        "fetched_at": "2026-05-22T10:01:00+00:00",
        "candles": _candles(),
    }


def test_auto_paper_returns_per_strategy_diagnostics(app_client, monkeypatch):
    import Backend.presentation.api.execution as execution_api
    from Backend.application.trading_service import TradingService

    monkeypatch.setattr(execution_api, "get_candles", lambda symbol, interval="1m", period="1d", limit=150: _market_response(interval))
    monkeypatch.setattr(TradingService, "run_strategy", lambda self, **kwargs: [])

    headers = admin_headers(app_client)
    response = app_client.post(
        "/execution/auto-paper",
        json={"symbol": "NIFTY", "strategies": ["amd", "breakout"]},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "no_trade"
    assert payload["symbol"] == "NIFTY"
    assert payload["reason"] == "No validated signal found across auto-scan strategies."
    assert set(payload["strategy_diagnostics"]) == {"amd", "breakout"}
    assert payload["strategy_diagnostics"]["amd"]["raw_signals"] == 0
    assert payload["validation"]["market_status"] == "MARKET CLOSED"


def test_auto_paper_submits_first_validated_signal(app_client, monkeypatch):
    import Backend.presentation.api.execution as execution_api
    from Backend.application.trading_service import TradingService

    signal = StrategySignal(
        strategy_name="AMD + FVG + Supply/Demand",
        symbol="NIFTY",
        side="BUY",
        entry_price=103,
        stop_loss=100,
        target_price=110,
        signal_time=datetime.fromisoformat("2026-05-22T15:30:00+05:30"),
        metadata={"score": 9, "quantity": 75},
    )

    monkeypatch.setattr(execution_api, "get_candles", lambda symbol, interval="1m", period="1d", limit=150: _market_response(interval))
    monkeypatch.setattr(TradingService, "run_strategy", lambda self, **kwargs: [signal] if kwargs["strategy_name"] == "amd" else [])
    monkeypatch.setattr(execution_api, "validate_signals", lambda raw, **kwargs: (raw, "live"))
    monkeypatch.setattr(execution_api, "diagnose_signal_run", lambda raw, **kwargs: ["validated"])
    monkeypatch.setattr(execution_api, "_market_aligned", lambda item: True)
    monkeypatch.setattr(
        execution_api,
        "decide_signal",
        lambda item, **kwargs: SimpleNamespace(
            score=9,
            regime="TRENDING",
            to_dict=lambda: {
                "allowed": True,
                "status": "ACTIVE",
                "reason": "OK",
                "score": 9,
                "regime": "TRENDING",
            },
        ),
    )
    monkeypatch.setattr(execution_api, "evaluate_risk_gate", lambda decision: SimpleNamespace(allowed=True, reason="OK"))
    monkeypatch.setattr(
        execution_api,
        "validate_execution_constraints",
        lambda item: SimpleNamespace(
            accepted=True,
            reason="OK",
            quantity=75,
            lot_size=75,
            notional=7725,
            required_margin=7725,
        ),
    )

    headers = admin_headers(app_client)
    response = app_client.post(
        "/execution/auto-paper",
        json={"symbol": "NIFTY", "strategies": ["amd", "breakout"]},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "paper_order_submitted"
    assert payload["strategy"] == "AMD + FVG + Supply/Demand"
    assert payload["signal"] == "BUY"
    assert payload["entry"] == 103
    assert payload["stop"] == 100
    assert payload["target"] == 110
    assert payload["reason"] == "OK"
    assert "amd" in payload["strategy_diagnostics"]
