from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from Backend.infrastructure.market_data.dhan_provider import _normalize_candles


IST = ZoneInfo("Asia/Kolkata")


def _ts(hour: int = 10, minute: int = 0) -> int:
    return int(datetime(2026, 9, 25, hour, minute, tzinfo=IST).timestamp())


def test_dhan_index_dict_payload_keeps_zero_volume_ohlc():
    raw = {
        "data": {
            "timestamp": [_ts()],
            "open": [24980.0],
            "high": [25025.0],
            "low": [24960.0],
            "close": [25010.0],
            "volume": [0],
        }
    }

    candles = _normalize_candles("NIFTY", raw)

    assert len(candles) == 1
    assert candles[0]["close"] == 25010.0
    assert candles[0]["volume"] == 0
    assert candles[0]["exchange_timezone"] == "Asia/Kolkata"


def test_dhan_index_list_payload_keeps_missing_volume():
    raw = {
        "data": [
            {
                "timestamp": _ts(),
                "open": 24980.0,
                "high": 25025.0,
                "low": 24960.0,
                "close": 25010.0,
            }
        ]
    }

    candles = _normalize_candles("BANKNIFTY", raw)

    assert len(candles) == 1
    assert candles[0]["volume"] == 0


def test_dhan_non_index_zero_volume_filter_is_preserved():
    raw = {
        "data": {
            "timestamp": [_ts()],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [0],
        }
    }

    assert _normalize_candles("RELIANCE", raw) == []


def test_dhan_candles_outside_nse_session_are_filtered():
    raw = {
        "data": {
            "timestamp": [_ts(8, 30)],
            "open": [24980.0],
            "high": [25025.0],
            "low": [24960.0],
            "close": [25010.0],
            "volume": [0],
        }
    }

    assert _normalize_candles("NIFTY", raw) == []
