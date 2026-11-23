from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from Backend.application import worker


class _MarketService:
    def __init__(self, timestamp=None):
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def get_candles(self, symbol, *, interval, period, limit):
        return {
            "candles": [
                {
                    "timestamp": self.timestamp,
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                }
            ]
        }


def test_periodic_auto_paper_skips_outside_market_hours(monkeypatch):
    worker._LAST_AUTO_PAPER_CANDLE.clear()
    monkeypatch.setattr(worker, "get_market_session", lambda: SimpleNamespace(market_live=False))

    called = []
    monkeypatch.setattr(worker, "_run_auto_paper_job", lambda payload: called.append(payload))

    result = worker._run_periodic_auto_paper()

    assert result == {"status": "outside_market_hours", "execution_mode": "paper"}
    assert called == []


def test_periodic_auto_paper_scans_each_candle_once(monkeypatch):
    worker._LAST_AUTO_PAPER_CANDLE.clear()
    monkeypatch.setattr(worker, "get_market_session", lambda: SimpleNamespace(market_live=True))
    # Both scans must see the exact same market candle; creating a fresh
    # service each call would generate a new timestamp and simulate new data.
    market_service = _MarketService()
    monkeypatch.setattr(worker, "get_market_data_service", lambda: market_service)

    calls = []

    def fake_auto_paper(payload):
        calls.append(payload)
        return {"status": "no_trade", "execution_mode": "paper"}

    monkeypatch.setattr(worker, "_run_auto_paper_job", fake_auto_paper)

    first = worker._run_periodic_auto_paper()
    second = worker._run_periodic_auto_paper()

    assert first["execution_mode"] == "paper"
    assert first["symbols"]["NIFTY"]["status"] == "no_trade"
    assert len(calls) == 1
    assert calls[0]["symbol"] == "NIFTY"
    assert calls[0]["interval"] == "1m"

    assert second["symbols"]["NIFTY"]["status"] == "already_scanned"
    assert len(calls) == 1


def test_auto_paper_worker_forces_paper_execution(monkeypatch):
    captured = []

    def fake_run_live_analysis(payload):
        captured.append(payload)
        return {"execution_mode": payload.execution_mode}

    monkeypatch.setattr(worker, "run_live_analysis", fake_run_live_analysis)

    result = worker._run_auto_paper_job(
        {
            "symbol": "NIFTY",
            "strategies": ["breakout"],
        }
    )

    assert result["execution_mode"] == "paper"
    assert len(captured) == 1
    assert captured[0].auto_trade is True
    assert captured[0].execution_mode == "paper"


def test_auto_paper_skips_stale_and_future_candles(monkeypatch):
    monkeypatch.setattr(worker, "get_market_session", lambda: SimpleNamespace(market_live=True))
    worker._LAST_AUTO_PAPER_CANDLE.clear()
    calls = []
    monkeypatch.setattr(worker, "_run_auto_paper_job", lambda payload: calls.append(payload))

    for timestamp in (
        (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    ):
        monkeypatch.setattr(worker, "get_market_data_service", lambda timestamp=timestamp: _MarketService(timestamp))
        result = worker._run_periodic_auto_paper()
        assert result["symbols"]["NIFTY"]["status"] == "stale_candle"

    assert calls == []
    assert worker._LAST_AUTO_PAPER_CANDLE == {}


def test_candle_ingestion_provenance_uses_provider_not_paper_demo_label():
    assert worker._candle_storage_source({
        "provider": "yahoo", "source": "demo",
    }) == "yahoo"
    assert worker._candle_storage_source({
        "provider_name": "dhan", "source": "live",
    }) == "dhan"
    assert worker._candle_storage_source({"source": "demo"}) == "demo"
    assert worker._candle_storage_source({}) == "unknown"


def test_auto_paper_retries_failed_analysis_on_same_candle(monkeypatch):
    worker._LAST_AUTO_PAPER_CANDLE.clear()
    monkeypatch.setattr(worker, "get_market_session", lambda: SimpleNamespace(market_live=True))
    market = _MarketService()
    monkeypatch.setattr(worker, "get_market_data_service", lambda: market)
    monkeypatch.setattr(worker, "_auto_paper_symbols", lambda: ["NIFTY"])
    responses = iter([
        {"strategies": {
            "breakout": {"error": "temporary failure"},
            "crt_tbs": {"trades": [{"status": "paper_simulated"}]},
        }},
        {"strategies": {"breakout": {"trades": [{"status": "paper_simulated"}]}}},
    ])
    monkeypatch.setattr(worker, "_run_auto_paper_job", lambda payload: next(responses))

    assert worker._run_periodic_auto_paper()["status"] == "partial_failure"
    assert worker._LAST_AUTO_PAPER_CANDLE == {}
    assert worker._run_periodic_auto_paper()["status"] == "completed"
    assert worker._run_periodic_auto_paper()["symbols"]["NIFTY"]["status"] == "already_scanned"


def test_auto_paper_provider_failure_does_not_block_other_symbols(monkeypatch):
    worker._LAST_AUTO_PAPER_CANDLE.clear()
    monkeypatch.setattr(worker, "get_market_session", lambda: SimpleNamespace(market_live=True))
    monkeypatch.setattr(worker, "_auto_paper_symbols", lambda: ["NIFTY", "BANKNIFTY"])

    class Market(_MarketService):
        def get_candles(self, symbol, **kwargs):
            if symbol == "NIFTY":
                raise RuntimeError("provider unavailable")
            return super().get_candles(symbol, **kwargs)

    monkeypatch.setattr(worker, "get_market_data_service", lambda: Market())
    calls = []

    def scan(payload):
        calls.append(payload["symbol"])
        return {"status": "no_trade"}

    monkeypatch.setattr(worker, "_run_auto_paper_job", scan)
    result = worker._run_periodic_auto_paper()
    assert result["status"] == "partial_failure"
    assert result["symbols"]["NIFTY"]["status"] == "market_data_error"
    assert calls == ["BANKNIFTY"]
    assert "NIFTY" not in worker._LAST_AUTO_PAPER_CANDLE
