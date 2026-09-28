from types import SimpleNamespace

from Backend.presentation.api import trading_api


class _DataQuality:
    def model_dump(self):
        return {}


def test_trading_signals_force_live_mode(monkeypatch):
    captured = {}

    class FakeService:
        def run_strategy(self, **kwargs):
            captured.update(kwargs)
            return []

    monkeypatch.setattr(trading_api, "TradingService", FakeService)
    monkeypatch.setattr(
        trading_api,
        "validate_candles",
        lambda candles, source=None: (candles, _DataQuality()),
    )
    monkeypatch.setattr(
        trading_api,
        "validate_signals",
        lambda signals, **kwargs: ([], "live"),
    )
    monkeypatch.setattr(trading_api, "diagnose_signal_run", lambda *args, **kwargs: [])
    monkeypatch.setattr(trading_api, "candle_freshness", lambda candles: {})
    monkeypatch.setattr(trading_api, "write_audit_log", lambda *args, **kwargs: None)

    payload = trading_api.StrategyRunRequest(
        strategy_name="breakout",
        symbol="NIFTY",
        capital=100000,
        risk_pct=1,
        rr_ratio=2,
        include_diagnostics=True,
        candle_source="dhan",
        candles=[
            {
                "timestamp": "2026-09-28T10:00:00+00:00",
                "open": 22800,
                "high": 22810,
                "low": 22790,
                "close": 22805,
                "volume": 0,
            }
        ],
    )

    trading_api.generate_signals(
        payload,
        _role="admin",
        request=None,
        actor=SimpleNamespace(id=1, username="tester", role="admin"),
        db=object(),
    )

    assert captured["params"]["live_mode"] is True
