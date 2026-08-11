from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from Backend.application.dataset_snapshot_service import DatasetSnapshotError, create_dataset_snapshot, dataset_hash
from Backend.core.database import Base
from Backend.domain.governance_models import DatasetSnapshot


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[DatasetSnapshot.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _candles():
    return [
        {"timestamp": "2025-01-01T09:16:00+05:30", "open": 101.0, "high": 103, "low": 100, "close": 102, "volume": 20},
        {"timestamp": "2025-01-01T09:15:00+05:30", "open": 100, "high": 102, "low": 99, "close": 101.0, "volume": 10},
    ]


def test_dataset_hash_is_deterministic_across_row_order_and_number_shapes():
    reversed_rows = list(reversed(_candles()))
    assert dataset_hash(_candles()) == dataset_hash(reversed_rows)


def test_dataset_snapshot_persists_actual_content_hash(db_session):
    snapshot = create_dataset_snapshot(
        db_session,
        candles=_candles(),
        provider="dhan",
        exchange="NSE",
        security_identifier="NIFTY",
        symbol="NIFTY",
        instrument="INDEX",
        timeframe="1m",
        timezone_name="Asia/Kolkata",
        source_metadata={"feed": "historical"},
    )

    assert snapshot.row_count == 2
    assert snapshot.dataset_hash == dataset_hash(_candles())
    assert snapshot.start_time < snapshot.end_time


def test_empty_dataset_is_rejected(db_session):
    with pytest.raises(DatasetSnapshotError, match="empty"):
        create_dataset_snapshot(
            db_session, candles=[], provider="dhan", exchange="NSE", security_identifier="NIFTY",
            symbol="NIFTY", instrument="INDEX", timeframe="1m", timezone_name="Asia/Kolkata",
        )
