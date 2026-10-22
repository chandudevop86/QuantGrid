from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from Backend.domain.signal_event_models import SignalEvaluationEvent
from Backend.application.signal_event_store import record_signal_evaluation_event


def event(**overrides):
    data = {
        "evaluation_id": "eval-1", "event_type": "SIGNAL_REJECTED",
        "signal_id": "sig-1", "strategy": "crt_tbs", "symbol": "NIFTY",
        "side": "SELL", "signal_time": "2026-10-22T09:05:00Z",
        "snapshot_time": "2026-10-22T09:05:00Z", "status": "REJECTED",
        "reason": "MTF_CONFLICT", "mtf_bias": "BULLISH", "evidence": {"score": 8},
    }
    data.update(overrides)
    return data


def test_repeated_signal_event_is_atomic_and_unique():
    engine = create_engine("sqlite://")
    SignalEvaluationEvent.__table__.create(engine)
    with Session(engine) as session:
        created_ids = [record_signal_evaluation_event(session, event()) for _ in range(100)]
        session.commit()
        assert created_ids[0][1] is True
        assert all(not inserted for _, inserted in created_ids[1:])
        assert len({row_id for row_id, _ in created_ids}) == 1


def test_changed_context_is_distinct_and_order_event_is_separate():
    engine = create_engine("sqlite://")
    SignalEvaluationEvent.__table__.create(engine)
    with Session(engine) as session:
        a = record_signal_evaluation_event(session, event())
        b = record_signal_evaluation_event(session, event(
            evaluation_id="eval-2", status="ACTIVE", reason="OK",
            mtf_bias="BEARISH", event_type="SIGNAL_ACCEPTED"))
        c = record_signal_evaluation_event(session, event(event_type="ORDER_REQUESTED"))
        session.commit()
        assert len({a[0], b[0], c[0]}) == 3


def test_missing_identifier_fails_closed():
    engine = create_engine("sqlite://")
    SignalEvaluationEvent.__table__.create(engine)
    with Session(engine) as session:
        try:
            record_signal_evaluation_event(session, event(evaluation_id=""))
        except ValueError:
            pass
        else:
            raise AssertionError("empty evaluation_id must be rejected")
