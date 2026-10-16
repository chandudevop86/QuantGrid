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
    validate_market_provenance,
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
    assert report["candidate_event_count"] > 0
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


def test_missing_index_volume_is_not_mistaken_for_observed_volume():
    raw = _bars("2026-10-12", 5)
    raw.loc[1, "volume"] = None
    normalized = normalize_candles(raw, source_minutes=5, timestamp_role="open")
    assert normalized["volume"].iloc[1] == 0.0


def test_real_market_replay_blocks_demo_provenance():
    raw = _bars("2026-10-12", 5)
    raw["source"] = "demo"
    with pytest.raises(ReplayDataError, match="demo"):
        validate_market_provenance(raw)


def test_real_market_replay_fails_closed_without_source_metadata():
    raw = _bars("2026-10-12", 5)
    with pytest.raises(ReplayDataError, match="Missing source column"):
        validate_market_provenance(raw)


def test_real_market_replay_blocks_mixed_demo_and_yahoo():
    raw = _bars("2026-10-12", 5)
    raw["source"] = ["yahoo", "demo", "yahoo", "demo", "yahoo"]
    with pytest.raises(ReplayDataError, match="demo"):
        validate_market_provenance(raw)


def test_recognized_provider_labels_are_not_claimed_as_verified():
    raw = _bars("2026-10-12", 5)
    raw["source"] = "yahoo"
    assert validate_market_provenance(raw) == {"yahoo": 5}


def test_unknown_provider_label_is_rejected_pending_review():
    raw = _bars("2026-10-12", 5)
    raw["source"] = "some-unknown-provider"
    with pytest.raises(ReplayDataError, match="Unverified"):
        validate_market_provenance(raw)


def test_october_first_style_second_offset_overlaps_are_rejected():
    """Nonzero-second bars cannot be averaged/rounded into one-minute OHLC."""
    raw = _bars("2026-10-12", 5)
    competing = raw.iloc[[0]].copy()
    competing.loc[competing.index[0], "timestamp"] = "2026-10-12T09:15:14+05:30"
    competing.loc[competing.index[0], "close"] += 34.05
    competing.loc[competing.index[0], "high"] += 40.00
    contaminated = pd.concat([raw, competing], ignore_index=True)
    with pytest.raises(ReplayDataError, match="Missing or irregular|outside aligned NSE"):
        normalize_candles(contaminated, source_minutes=1, timestamp_role="open")


def test_october_fifteenth_style_fourteen_minute_hole_is_rejected():
    raw = _bars("2026-10-12", 30, minutes=1)
    # Missing minutes must fail, not be silently interpolated into an FVG.
    raw = raw.drop(index=range(13, 27)).reset_index(drop=True)
    with pytest.raises(ReplayDataError, match="Missing or irregular"):
        normalize_candles(raw, source_minutes=1, timestamp_role="open")
