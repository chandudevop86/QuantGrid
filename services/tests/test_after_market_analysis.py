from datetime import datetime
from types import SimpleNamespace

from Backend.application.live_analysis_worker import LiveAnalysisPayload, run_live_analysis
from Backend.domain.models.signal import StrategySignal


def _closed_market_response(interval: str = "1m") -> dict:
    return {
        "symbol": "NIFTY",
        "market_symbol": "^NSEI",
        "interval": interval,
        "period": "1d",
        "source": "yahoo-finance",
        "volume_status": "reported",
        "fetched_at": "2026-05-22T10:02:00+00:00",
        "candles": [
            {"timestamp": "2026-05-22T15:28:00+05:30", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
            {"timestamp": "2026-05-22T15:29:00+05:30", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 1000},
            {"timestamp": "2026-05-22T15:30:00+05:30", "open": 102, "high": 104, "low": 101, "close": 103, "volume": 1000},
        ],
    }


def test_after_market_analysis_allowed_but_live_execution_blocked(monkeypatch):
    import Backend.application.live_analysis_worker as worker

    signal = StrategySignal(
        strategy_name="breakout",
        symbol="NIFTY",
        side="BUY",
        entry_price=103,
        stop_loss=100,
        target_price=110,
        signal_time=datetime.fromisoformat("2026-05-22T15:30:00+05:30"),
        metadata={"score": 9},
    )

    requested_intervals = []

    def fake_get_candles(symbol, interval="1m", period="1d"):
        requested_intervals.append((interval, period))
        return _closed_market_response(interval)

    def fake_run_strategy(self, **kwargs):
        assert kwargs["params"]["h1_candles"]
        return [signal]

    monkeypatch.setattr(worker, "get_candles", fake_get_candles)
    monkeypatch.setattr(worker.TradingService, "run_strategy", fake_run_strategy)
    monkeypatch.setattr(worker, "split_signals", lambda signals, **kwargs: (signals, [], []))
    monkeypatch.setattr(worker, "validate_signals", lambda signals, **kwargs: (signals, "live"))
    monkeypatch.setattr(worker, "analyze_market_structure", lambda candles, **kwargs: {"trade_decision": "WAIT"})
    monkeypatch.setattr(
        worker,
        "validate_live_candle",
        lambda *args, **kwargs: SimpleNamespace(
            valid=True,
            valid_for_analysis=True,
            valid_for_execution=False,
            market_status="MARKET CLOSED",
            model_dump=lambda: {
                "valid": True,
                "valid_for_analysis": True,
                "valid_for_execution": False,
                "market_status": "MARKET CLOSED",
            },
        ),
    )

    result = run_live_analysis(
        LiveAnalysisPayload(symbol="NIFTY", strategy="breakout", auto_trade=False, execution_mode="paper")
    )

    assert result["validation"]["market_status"] == "MARKET CLOSED"
    assert result["validation"]["valid_for_analysis"] is True
    assert result["validation"]["valid_for_execution"] is False
    assert result["signals"][0]["symbol"] == "NIFTY"
    assert ("1h", "5d") in requested_intervals

    try:
        run_live_analysis(
            LiveAnalysisPayload(symbol="NIFTY", strategy="breakout", auto_trade=True, execution_mode="live")
        )
    except ValueError as exc:
        assert "only paper execution is supported" in str(exc)
    else:
        raise AssertionError("live execution after market close should be blocked")


def test_after_market_auto_paper_does_not_create_trade(monkeypatch):
    import Backend.application.live_analysis_worker as worker

    signal = StrategySignal(
        strategy_name="breakout",
        symbol="NIFTY",
        side="BUY",
        entry_price=103,
        stop_loss=100,
        target_price=110,
        signal_time=datetime.fromisoformat("2026-05-22T15:30:00+05:30"),
        metadata={"score": 9},
    )

    monkeypatch.setattr(worker, "get_candles", lambda *args, **kwargs: _closed_market_response(kwargs.get("interval", "1m")))
    monkeypatch.setattr(worker.TradingService, "run_strategy", lambda self, **kwargs: [signal])
    monkeypatch.setattr(worker, "split_signals", lambda signals, **kwargs: (signals, [], []))
    monkeypatch.setattr(worker, "validate_signals", lambda signals, **kwargs: (signals, "live"))
    monkeypatch.setattr(worker, "analyze_market_structure", lambda candles, **kwargs: {"trade_decision": "WAIT"})
    monkeypatch.setattr(worker, "kill_switch_status", lambda: {"active": False, "reason": None})
    monkeypatch.setattr(
        worker,
        "validate_live_candle",
        lambda *args, **kwargs: SimpleNamespace(
            valid=True,
            valid_for_analysis=True,
            valid_for_execution=False,
            market_status="MARKET CLOSED",
            model_dump=lambda: {
                "valid": True,
                "valid_for_analysis": True,
                "valid_for_execution": False,
                "market_status": "MARKET CLOSED",
            },
        ),
    )
    created = []
    monkeypatch.setattr(worker, "_generate_paper_trades", lambda signals: created.append(signals) or [{"status": "paper_simulated"}])

    result = run_live_analysis(
        LiveAnalysisPayload(symbol="NIFTY", strategy="breakout", auto_trade=True, execution_mode="paper")
    )

    assert result["trades"] == []
    assert result["auto_trade_blocked_reason"] == "MARKET_DATA_NOT_EXECUTABLE: MARKET CLOSED"
    assert created == []


def test_stale_demo_data_cannot_create_auto_paper_trade(monkeypatch):
    import Backend.application.live_analysis_worker as worker

    stale_response = _closed_market_response()
    stale_response["source"] = "demo"

    signal = StrategySignal(
        strategy_name="breakout",
        symbol="NIFTY",
        side="BUY",
        entry_price=103,
        stop_loss=100,
        target_price=110,
        signal_time=datetime.fromisoformat("2026-05-22T15:30:00+05:30"),
        metadata={"score": 9},
    )

    monkeypatch.setattr(worker, "get_candles", lambda *args, **kwargs: {**stale_response, "interval": kwargs.get("interval", "1m")})
    monkeypatch.setattr(worker.TradingService, "run_strategy", lambda self, **kwargs: [signal])
    monkeypatch.setattr(worker, "split_signals", lambda signals, **kwargs: (signals, [], []))
    monkeypatch.setattr(worker, "validate_signals", lambda signals, **kwargs: (signals, "demo"))
    monkeypatch.setattr(worker, "analyze_market_structure", lambda candles, **kwargs: {"trade_decision": "WAIT"})
    monkeypatch.setattr(worker, "kill_switch_status", lambda: {"active": False, "reason": None})
    monkeypatch.setattr(
        worker,
        "validate_live_candle",
        lambda *args, **kwargs: SimpleNamespace(
            valid=False,
            valid_for_analysis=True,
            valid_for_execution=False,
            market_status="DELAYED FEED",
            model_dump=lambda: {
                "valid": False,
                "valid_for_analysis": True,
                "valid_for_execution": False,
                "market_status": "DELAYED FEED",
            },
        ),
    )
    created = []
    monkeypatch.setattr(worker, "_generate_paper_trades", lambda signals: created.append(signals) or [{"status": "paper_simulated"}])

    result = run_live_analysis(
        LiveAnalysisPayload(symbol="NIFTY", strategy="breakout", auto_trade=True, execution_mode="paper")
    )

    assert result["trades"] == []
    assert result["auto_trade_blocked_reason"] == "MARKET_DATA_NOT_EXECUTABLE: DELAYED FEED"
    assert created == []


def test_kill_switch_blocks_worker_auto_paper_trade(monkeypatch):
    import Backend.application.live_analysis_worker as worker

    signal = StrategySignal(
        strategy_name="breakout",
        symbol="NIFTY",
        side="BUY",
        entry_price=103,
        stop_loss=100,
        target_price=110,
        signal_time=datetime.fromisoformat("2026-05-22T15:30:00+05:30"),
        metadata={"score": 9},
    )

    monkeypatch.setattr(worker, "get_candles", lambda *args, **kwargs: _closed_market_response(kwargs.get("interval", "1m")))
    monkeypatch.setattr(worker.TradingService, "run_strategy", lambda self, **kwargs: [signal])
    monkeypatch.setattr(worker, "split_signals", lambda signals, **kwargs: (signals, [], []))
    monkeypatch.setattr(worker, "validate_signals", lambda signals, **kwargs: (signals, "live"))
    monkeypatch.setattr(worker, "analyze_market_structure", lambda candles, **kwargs: {"trade_decision": "WAIT"})
    monkeypatch.setattr(worker, "kill_switch_status", lambda: {"active": True, "reason": "operator halt"})
    monkeypatch.setattr(
        worker,
        "validate_live_candle",
        lambda *args, **kwargs: SimpleNamespace(
            valid=True,
            valid_for_analysis=True,
            valid_for_execution=True,
            market_status="LIVE MARKET",
            model_dump=lambda: {
                "valid": True,
                "valid_for_analysis": True,
                "valid_for_execution": True,
                "market_status": "LIVE MARKET",
            },
        ),
    )
    created = []
    monkeypatch.setattr(worker, "_generate_paper_trades", lambda signals: created.append(signals) or [{"status": "paper_simulated"}])

    result = run_live_analysis(
        LiveAnalysisPayload(symbol="NIFTY", strategy="breakout", auto_trade=True, execution_mode="paper")
    )

    assert result["trades"] == []
    assert result["auto_trade_blocked_reason"] == "KILL_SWITCH_ACTIVE: operator halt"
    assert created == []
