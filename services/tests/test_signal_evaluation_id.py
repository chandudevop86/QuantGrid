from Backend.application.signal_evaluation_id import signal_evaluation_id


SIGNAL = {
    "strategy_name": "crt_tbs",
    "symbol": "NIFTY",
    "signal": "SELL",
    "timestamp": "2026-10-22T09:05:00Z",
    "entry_price": 22672.55,
    "stop_loss": 22701.088,
    "target_price": 22615.4739,
}


def test_repeated_identical_evaluations_have_stable_id():
    decision = {"status": "ACTIVE", "reason": "OK", "mtf_bias": "BEARISH"}
    first = signal_evaluation_id(SIGNAL, decision, "2026-10-22T09:05:00Z")
    assert first == signal_evaluation_id(dict(SIGNAL), dict(decision), "2026-10-22T09:05:00Z")
    assert len(first) == 24


def test_changed_bias_and_decision_have_different_ids():
    allowed = signal_evaluation_id(SIGNAL, {"status": "ACTIVE", "reason": "OK", "mtf_bias": "BEARISH"}, "t1")
    rejected = signal_evaluation_id(SIGNAL, {"status": "REJECTED", "reason": "MTF_CONFLICT", "mtf_bias": "BULLISH"}, "t1")
    assert allowed != rejected


def test_new_market_snapshot_changes_evaluation_id():
    decision = {"status": "ACTIVE", "reason": "OK", "mtf_bias": "BEARISH"}
    assert signal_evaluation_id(SIGNAL, decision, "t1") != signal_evaluation_id(SIGNAL, decision, "t2")
