from datetime import datetime, timedelta, timezone
from Backend.application.options.execution_preflight import (
    verify_quote_freshness, verify_lot_size, verify_premium_exposure,
)


def test_missing_timestamp_never_passes():
    assert not verify_quote_freshness(None)
    assert not verify_quote_freshness("")


def test_stale_and_future_quotes_fail():
    now = datetime.now(timezone.utc)
    assert not verify_quote_freshness((now-timedelta(seconds=31)).isoformat(), now=now)
    assert not verify_quote_freshness((now+timedelta(seconds=1)).isoformat(), now=now)
    assert verify_quote_freshness((now-timedelta(seconds=5)).isoformat(), now=now)


def test_exchange_lot_size_must_match():
    assert verify_lot_size(contract_lot_size=65, exchange_lot_size=65)
    assert not verify_lot_size(contract_lot_size=50, exchange_lot_size=65)
    assert not verify_lot_size(contract_lot_size=65, exchange_lot_size=None)


def test_premium_exposure_includes_pending():
    assert not verify_premium_exposure(ask=60, lot_size=65, lots=1,
                                       existing=0, pending=2000, limit=5000)
    assert verify_premium_exposure(ask=60, lot_size=65, lots=1,
                                   existing=0, pending=0, limit=5000)
