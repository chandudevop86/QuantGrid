"""Closed-bar replay tests; synthetic candles exercise timing, not profitability."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.replay_nifty_smc import (
    ReplayDataError,
    make_report,
    normalize_candles,
    replay,
    resample_complete,
)


def _bars(day: str, count: int, minutes: int = 5, tz: str = "Asia/Kolkata") -> pd.DataFrame:
    origin = pd.Timestamp(f"{day} 09:15:00", tz=tz)
    rows = []
    for i in range(count):
        opening = 23000 + i * 1.5
        rows.append({
            "timestamp": (origin + pd.Timedelta(minutes=i * minutes)).isoformat(),
            "open": opening, "high": opening + 4, "low": opening - 3,
            "close": opening + 2, "volume": 1200,
        })
    return pd.DataFrame(rows)


def _prepared(days: tuple[str, ...], count: int = 45) -> pd.DataFrame:
    raw = pd.concat([_bars(day, count) for day in days], ignore_index=True)
    return normalize_candles(raw, source_minutes=5, timestamp_role="open")


def test_nse_15m_aggregation_never_uses_incomplete_5m_bars():
    frame = _prepared(("2026-10-12",), count=7)
    fifteen = resample_complete(frame, source_minutes=5, target_minutes=15)
    assert len(fifteen) == 2
    assert fifteen["timestamp"].iloc[0] == frame["timestamp"].iloc[0]
    assert fifteen["close"].iloc[0] == frame["close"].iloc[2]
    assert fifteen["close"].iloc[1] == frame["close"].iloc[5]


def test_one_minute_source_only_constructs_complete_five_minute_groups():
    frame = normalize_candles(_bars("2026-10-12", 11, minutes=1), source_minutes=1, timestamp_role="open")
    five = resample_complete(frame, source_minutes=1, target_minutes=5)
    assert len(five) == 2
    assert five["open"].iloc[0] == frame["open"].iloc[0]
    assert five["close"].iloc[1] == frame["close"].iloc[9]


def test_replay_is_prefix_invariant_with_more_future_candles():
    frame = _prepared(("2026-10-12", "2026-10-13"), count=45)
    report = make_report(frame, source="synthetic_fixture_NOT_MARKET_DATA")
    assert report["prefix_invariance"] == "PASS"
    assert report["complete_5m_bars"] == 90
    assert report["complete_15m_bars"] == 30
    earlier = replay(frame.iloc[:45])
    cutoff = frame["timestamp"].iloc[44] + pd.Timedelta(minutes=5)
    full_before_cutoff = [
        x for x in replay(frame)
        if pd.Timestamp(x["asof_close_utc"]) <= cutoff
    ]
    assert full_before_cutoff == earlier
    assert all(x["status"] == "AUDIT_ONLY_NOT_AN_ORDER" for x in report["candidate_events"])


def test_rejects_ambiguous_timestamps_and_duplicate_bars():
    raw = _bars("2026-10-12", 5)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"]).dt.tz_localize(None)
    with pytest.raises(ReplayDataError, match="Naive timestamps"):
        normalize_candles(raw, source_minutes=5, timestamp_role="open")
    raw = _bars("2026-10-12", 5)
    raw = pd.concat([raw, raw.iloc[[0]]], ignore_index=True)
    with pytest.raises(ReplayDataError, match="Duplicate"):
        normalize_candles(raw, source_minutes=5, timestamp_role="open")


def test_rejects_ohlc_corruption_and_out_of_session():
    raw = _bars("2026-10-12", 5)
    raw.loc[2, "high"] = raw.loc[2, "low"] - 1
    with pytest.raises(ReplayDataError, match="Impossible"):
        normalize_candles(raw, source_minutes=5, timestamp_role="open")
    after_hours = _bars("2026-10-12", 1)
    after_hours.loc[0, "timestamp"] = "2026-10-12T15:30:00+05:30"
    with pytest.raises(ReplayDataError, match="outside aligned NSE"):
        normalize_candles(after_hours, source_minutes=5, timestamp_role="open")


def test_close_timestamp_convention_maps_to_open_time():
    frame = _bars("2026-10-12", 5)
    opens = normalize_candles(frame, source_minutes=5, timestamp_role="open")
    frame["timestamp"] = (
        pd.to_datetime(frame["timestamp"]) + pd.Timedelta(minutes=5)
    ).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    close_stamped = normalize_candles(frame, source_minutes=5, timestamp_role="close")
    assert opens["timestamp"].tolist() == close_stamped["timestamp"].tolist()


def test_insufficient_history_aborts_instead_of_claiming_success():
    frame = _prepared(("2026-10-12",), count=15)
    with pytest.raises(ReplayDataError, match="Insufficient"):
        make_report(frame, source="fixture")


def test_missing_intraday_bar_fails_closed():
    raw = _bars("2026-10-12", 7).drop(index=3).reset_index(drop=True)
    with pytest.raises(ReplayDataError, match="Missing or irregular"):
        normalize_candles(raw, source_minutes=5, timestamp_role="open")
