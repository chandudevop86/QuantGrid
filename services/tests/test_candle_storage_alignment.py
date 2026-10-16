"""Prevent intraminute quote snapshots from contaminating candle storage."""
from Backend.application import market_data_store


def _bar(timestamp, value=22360.05):
    return {
        "timestamp": timestamp,
        "open": value - 4,
        "high": value + 5,
        "low": value - 6,
        "close": value,
        "volume": 0,
    }


def test_storage_rejects_october_first_style_offset_seconds(monkeypatch):
    batches = []
    monkeypatch.setattr(market_data_store, "init_market_data_store", lambda: None)
    monkeypatch.setattr(market_data_store, "_use_sqlite", lambda: False)
    monkeypatch.setattr(
        market_data_store,
        "_db_store_candles",
        lambda **kwargs: batches.append(kwargs),
    )
    aligned = _bar("2026-10-01T09:03:00+00:00")
    tick_snapshot = _bar("2026-10-01T09:03:15+00:00", 22326)
    market_data_store.store_candles(
        symbol="NIFTY", market_symbol="^NSEI", interval="1m",
        source="yahoo", candles=[aligned, tick_snapshot],
    )
    assert len(batches) == 1
    assert batches[0]["candles"] == [aligned]
    assert batches[0]["source"] == "yahoo"


def test_storage_drops_entire_offset_only_batch_without_writing(monkeypatch):
    writes = []
    monkeypatch.setattr(market_data_store, "init_market_data_store", lambda: writes.append("init"))
    monkeypatch.setattr(market_data_store, "_use_sqlite", lambda: False)
    monkeypatch.setattr(
        market_data_store, "_db_store_candles",
        lambda **kwargs: writes.append(kwargs),
    )
    market_data_store.store_candles(
        symbol="NIFTY", market_symbol="^NSEI", interval="1m",
        source="demo", candles=[_bar("2026-10-01T09:03:15+00:00")],
    )
    assert writes == []


def test_storage_rejects_offset_seconds_for_other_intraday_intervals():
    for interval in ("1", "5m", "15m", "60m"):
        assert market_data_store._aligned_candles_for_storage(
            [_bar("2026-10-01T09:15:14+05:30")], interval,
        ) == []
        assert len(market_data_store._aligned_candles_for_storage(
            [_bar("2026-10-01T09:15:00+05:30")], interval,
        )) == 1


def test_storage_does_not_filter_daily_candles_by_minute_alignment():
    row = _bar("2026-10-01T10:01:12+00:00")
    assert market_data_store._aligned_candles_for_storage([row], "1d") == [row]


def test_storage_rejects_unparseable_intraday_timestamps():
    assert market_data_store._aligned_candles_for_storage(
        [_bar("unknown")], "1m",
    ) == []
