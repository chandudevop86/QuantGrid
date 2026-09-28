from Backend.application import worker


class _MarketService:
    def __init__(self, timestamp="2026-09-28T10:00:00+00:00"):
        self.timestamp = timestamp

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
    monkeypatch.setattr(worker, "is_market_hours_ist", lambda: False)

    called = []
    monkeypatch.setattr(worker, "_run_auto_paper_job", lambda payload: called.append(payload))

    result = worker._run_periodic_auto_paper()

    assert result == {"status": "outside_market_hours", "execution_mode": "paper"}
    assert called == []


def test_periodic_auto_paper_scans_each_candle_once(monkeypatch):
    worker._LAST_AUTO_PAPER_CANDLE.clear()
    monkeypatch.setattr(worker, "is_market_hours_ist", lambda: True)
    monkeypatch.setattr(worker, "get_market_data_service", lambda: _MarketService())

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
