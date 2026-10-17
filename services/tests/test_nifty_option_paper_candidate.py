"""No paper option candidate may silently become a spot or live order."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from Backend.domain.models.signal import StrategySignal


def signal(side="BUY"):
    return StrategySignal(
        strategy_name="breakout", symbol="NIFTY", side=side,
        entry_price=25000.0, stop_loss=24950.0, target_price=25100.0,
        signal_time=datetime.now(timezone.utc), metadata={"score": 9},
    )


def test_candidate_resolves_ce_or_pe_from_verified_dhan_chain(monkeypatch):
    from Backend.presentation.api import market_api
    import Backend.application.live_analysis_worker as worker
    now = datetime.now(timezone.utc)
    chain = {
        "symbol": "NIFTY", "source": "dhan-option-chain",
        "provider_available": True, "live_rows_available": True,
        "data_quality": {"status": "PASS"},
        "updated_at": (now - timedelta(seconds=5)).isoformat(),
        "expiry": (now + timedelta(days=5)).date().isoformat(),
        "atm_strike": 25000,
        "rows": [{
            "strike": 25000,
            "ce": {"security_id": "12345", "bid": {"price": 100}, "ask": {"price": 101}, "volume": 2000},
            "pe": {"security_id": "22345", "bid": {"price": 120}, "ask": {"price": 121}, "volume": 2000},
        }],
    }
    monkeypatch.setattr(market_api, "get_option_chain", lambda *a, **kw: chain)
    call = worker._paper_option_candidate([signal("BUY")])
    put = worker._paper_option_candidate([signal("SELL")])
    assert call["security_id"] == "12345"
    assert put["security_id"] == "22345"
    assert call["execution_approved"] is False
    assert put["execution_approved"] is False


def test_opt_in_option_paper_analysis_never_places_spot_simulated_trade(monkeypatch):
    import Backend.application.live_analysis_worker as worker

    monkeypatch.setenv("QUANTGRID_AUTO_OPTION_PAPER_CANDIDATES", "true")
    candles = [
        {"timestamp": datetime.now(timezone.utc).isoformat(), "open": 25000,
         "high": 25005, "low": 24995, "close": 25001, "volume": 1500}
    ]
    monkeypatch.setattr(worker, "get_candles", lambda *args, **kwargs: {
        "symbol": "NIFTY", "source": "dhan", "candles": candles,
    })
    monkeypatch.setattr(worker.TradingService, "run_strategy", lambda self, **kwargs: [signal()])
    monkeypatch.setattr(worker, "split_signals", lambda signals, **kwargs: (signals, [], []))
    monkeypatch.setattr(worker, "validate_signals", lambda signals, **kwargs: (signals, "dhan"))
    monkeypatch.setattr(worker, "analyze_market_structure", lambda candles, **kwargs: {})
    monkeypatch.setattr(worker, "kill_switch_status", lambda: {"active": False})
    monkeypatch.setattr(worker, "validate_live_candle", lambda *args, **kwargs: SimpleNamespace(
        valid_for_execution=True, market_status="LIVE MARKET",
        model_dump=lambda: {"valid_for_execution": True, "market_status": "LIVE MARKET"},
    ))
    monkeypatch.setattr(worker, "_paper_option_candidate", lambda signals: {
        "status": "candidate_only", "security_id": "12345", "execution_approved": False,
    })

    def cannot_simulate_spot(signals):
        raise AssertionError("spot order must not be simulated as an option")

    monkeypatch.setattr(worker, "_generate_paper_trades", cannot_simulate_spot)
    # Import through the patched worker module, not an early collection-time
    # function reference that can survive test-suite module reloading.
    result = worker.run_live_analysis(worker.LiveAnalysisPayload(symbol="NIFTY", auto_trade=True, execution_mode="paper"))
    assert result["trades"] == []
    assert result["option_candidate"]["security_id"] == "12345"
    assert result["auto_trade_blocked_reason"] == "NIFTY_OPTION_CANDIDATE_ONLY_NO_EXECUTION"
