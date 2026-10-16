"""Contract tests for read-only NIFTY Dhan/Yahoo historical quote comparison."""
from __future__ import annotations

import json
import sys

import pandas as pd
import pytest

from scripts import compare_nifty_providers as compare


def _bars(day: str, *, count: int = 40, price: float = 23000.0):
    start = pd.Timestamp(f"{day} 09:15:00", tz="Asia/Kolkata")
    return pd.DataFrame([
        {
            "timestamp": (start + pd.Timedelta(minutes=i)).isoformat(),
            "open": price + i,
            "high": price + i + 3,
            "low": price + i - 2,
            "close": price + i + 1,
            "volume": 0,
        }
        for i in range(count)
    ])


def test_compare_rejects_october_first_offset_second_flat_snapshots():
    raw = _bars("2026-10-01")
    offset = raw.iloc[:1].copy()
    offset["timestamp"] = "2026-10-01T09:15:15+05:30"
    offset["open"] = 22326.0
    offset["high"] = 22326.0
    offset["low"] = 22326.0
    offset["close"] = 22326.0
    data = pd.concat([raw, offset], ignore_index=True)
    clean, profile = compare.audit_bars(
        data, label="stored", start="2026-10-01", end="2026-10-01",
    )
    assert profile["offset_second_rows"] == 1
    assert profile["eligible_bars"] == len(raw)
    assert clean["timestamp"].is_unique
    assert not (clean["close"] == 22326).any()


def test_october_fifteenth_fourteen_minute_gap_reported_without_filling():
    raw = _bars("2026-10-15", count=375).drop(index=range(150, 164))
    clean, profile = compare.audit_bars(
        raw, label="dhan", start="2026-10-15", end="2026-10-15",
    )
    day = profile["days"]["2026-10-15"]
    assert len(clean) == 361
    assert day["missing_minutes"] == 14
    assert day["missing_sample"][0] == "11:45"
    assert day["missing_sample"][-1] == "11:58"


def test_discard_1530_and_unfinished_candle():
    raw = _bars("2026-10-15", count=375)
    raw = pd.concat([raw, pd.DataFrame([{
        "timestamp": "2026-10-15T15:30:00+05:30",
        "open": 23000, "high": 23002, "low": 22998,
        "close": 23001, "volume": 0,
    }])], ignore_index=True)
    clean, profile = compare.audit_bars(
        raw, label="dhan", start="2026-10-15", end="2026-10-15",
    )
    assert len(clean) == 375
    assert profile["out_of_session"] == 1
    now = pd.Timestamp("2026-10-15 09:18:20", tz="Asia/Kolkata")
    past, _ = compare.audit_bars(
        raw, label="dhan", start="2026-10-15", end="2026-10-15",
        now=now,
    )
    assert len(past) == 3


def test_duplicate_timestamp_both_rows_are_excluded_not_randomly_selected():
    frame = _bars("2026-10-01")
    duplicate = frame.iloc[[0]].copy()
    duplicate.loc[duplicate.index[0], "close"] += 1
    joined = pd.concat([frame, duplicate], ignore_index=True)
    clean, stats = compare.audit_bars(joined, label="stored", start="2026-10-01", end="2026-10-01")
    assert stats["duplicate_timestamp_rows_excluded"] == 2
    assert len(clean) == 39


def test_matching_40_bar_sample_reports_agreement_but_not_profit():
    dhan, _ = compare.audit_bars(
        _bars("2026-10-01"), label="dhan", start="2026-10-01", end="2026-10-01",
    )
    other = dhan.copy()
    other["close"] = other["close"] + 0.25
    result = compare.compare_bars(dhan, other, label="dhan_vs_yahoo", tolerance=0.5)
    assert result["result"] == "OHLC_AGREEMENT"
    assert result["matched_minutes"] == 40
    assert result["different_close_count"] == 0
    assert result["per_ist_date"]["2026-10-01"]["matched_minutes"] == 40


def test_mismatch_above_tolerance_is_flagged_with_absolute_price_diff():
    dhan, _ = compare.audit_bars(
        _bars("2026-10-01"), label="dhan", start="2026-10-01", end="2026-10-01",
    )
    other = dhan.copy()
    other.loc[20, "close"] += 34.05
    result = compare.compare_bars(dhan, other, label="dhan_vs_stored")
    assert result["result"] == "DISAGREEMENT"
    assert result["different_close_count"] == 1
    assert result["maximum_abs_close_difference_points"] == 34.05


def test_short_overlap_cannot_pass():
    dhan, _ = compare.audit_bars(
        _bars("2026-10-01"), label="dhan", start="2026-10-01", end="2026-10-01",
    )
    assert compare.compare_bars(
        dhan, dhan.iloc[:10], label="test",
    )["result"] == "INSUFFICIENT_OVERLAP"
    assert compare.compare_bars(
        dhan, pd.DataFrame(columns=dhan.columns), label="test",
    )["result"] == "INSUFFICIENT_OVERLAP"


def test_yahoo_chart_parsing_drops_unfinished_or_null_bars(monkeypatch):
    from Backend.infrastructure.market_data.yahoo_provider import YahooProvider
    t = int(pd.Timestamp("2026-10-15 09:15", tz="Asia/Kolkata").timestamp())
    chart = {
        "timestamp": [t, t + 60],
        "indicators": {"quote": [{
            "open": [100, None], "high": [102, None],
            "low": [99, None], "close": [101, None], "volume": [0, 0],
        }]},
    }
    monkeypatch.setattr(YahooProvider, "fetch_chart", lambda self, *args, **kwargs: chart)
    frame = compare.fetch_yahoo()
    assert len(frame) == 1
    assert frame["close"].iloc[0] == 101


def test_no_credential_exposure_and_no_database_write(monkeypatch, tmp_path):
    monkeypatch.setattr(compare, "fetch_dhan", lambda *args, **kwargs: _bars("2026-10-15"))
    monkeypatch.setattr(compare, "fetch_yahoo", lambda: _bars("2026-10-15"))
    monkeypatch.setattr(compare, "fetch_stored", lambda *args, **kwargs: _bars("2026-10-15"))
    report = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", [
        "compare_nifty_providers.py", "--start", "2026-10-15", "--end", "2026-10-15",
        "--include-stored", "--output", str(report),
    ])
    assert compare.main() == 0
    data = json.loads(report.read_text())
    assert data["status"] == "RESEARCH_ONLY_NO_LIVE_OR_PROFIT_APPROVAL"
    assert data["comparisons"][0]["matched_minutes"] == 40
    assert data["comparisons"][1]["matched_minutes"] == 40


def test_date_range_and_access_inputs_validate():
    with pytest.raises(compare.ProviderComparisonError, match="End date"):
        compare.utc_window("2026-10-16", "2026-10-01")


def test_bos_high_disagreement_flagged_even_when_closes_match():
    dhan, _ = compare.audit_bars(
        _bars("2026-10-01"), label="dhan", start="2026-10-01", end="2026-10-01",
    )
    other = dhan.copy()
    other.loc[20, "high"] = other.loc[20, "high"] + 16
    result = compare.compare_bars(dhan, other, label="dhan_vs_yahoo")
    assert result["result"] == "DISAGREEMENT"
    assert result["different_close_count"] == 0
    assert result["different_ohlc_count"] == 1
    assert result["max_abs_difference_by_ohlc_field"]["high"] == 16.0
    assert result["per_ist_date"]["2026-10-01"]["different_ohlc_count"] == 1


@pytest.mark.parametrize(("payload", "expected"), [
    ({"status": "failure", "errorCode": "DH-901"}, "AUTHENTICATION (DH-901)"),
    ({"status": "failure", "errorCode": "806"}, "DATA_API_SUBSCRIPTION (806)"),
    ({"status": "failure", "data": {"errorCode": "DH-904"}}, "RATE_LIMIT (DH-904)"),
    ({"status": "failure", "remarks": "Expecting value: line 1 column 1 (char 0)"}, "SDK_RESPONSE_JSON_PARSE_FAILURE"),
    ({"status": "failure", "remarks": "private_token-DO_NOT_ECHO"}, "UNKNOWN_DHAN_PROVIDER_FAILURE"),
])
def test_safe_dhan_failure_classification_never_echoes_raw_response(payload, expected):
    actual = compare.classify_dhan_failure(payload)
    assert actual == expected
    assert "private_token" not in actual


def test_failed_dhan_keeps_yahoo_and_stored_audit_without_claiming_success(monkeypatch, tmp_path):
    monkeypatch.setattr(compare, "fetch_dhan", lambda *args, **kwargs: (
        (_ for _ in ()).throw(compare.ProviderComparisonError(
            "Dhan request rejected: SDK_RESPONSE_JSON_PARSE_FAILURE"
        ))
    ))
    monkeypatch.setattr(compare, "fetch_yahoo", lambda: _bars("2026-10-15"))
    monkeypatch.setattr(compare, "fetch_stored", lambda *args, **kwargs: _bars("2026-10-15"))
    report = tmp_path / "partial.json"
    monkeypatch.setattr(sys, "argv", [
        "compare_nifty_providers.py", "--start", "2026-10-15", "--end", "2026-10-15",
        "--include-stored", "--output", str(report),
    ])
    assert compare.main() == 2  # Not a successful data comparison.
    saved = json.loads(report.read_text())
    assert saved["status"] == "PARTIAL_DHAN_UNAVAILABLE_NO_VALIDATION"
    assert saved["provider_profiles"]["yahoo"]["eligible_bars"] == 40
    assert saved["provider_profiles"]["stored_postgres"]["eligible_bars"] == 40
    assert saved["comparisons"][0]["result"] == "INSUFFICIENT_OVERLAP"
    assert saved["comparisons"][1]["result"] == "INSUFFICIENT_OVERLAP"
    assert saved["comparisons"][2]["pair"] == "yahoo_vs_existing_postgres"
    assert saved["comparisons"][2]["result"] == "OHLC_AGREEMENT"
    assert saved["comparisons"][2]["matched_minutes"] == 40
    assert "independent validation" in saved["comparisons"][2]["evidence_note"]
    assert "SDK_RESPONSE_JSON_PARSE_FAILURE" in saved["dhan_error_category"]


def test_failed_dhan_unknown_sdk_exception_is_not_leaked(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise RuntimeError("raw response contains TOP_SECRET_ACCESS_TOKEN")

    monkeypatch.setattr(compare, "fetch_dhan", fail)
    monkeypatch.setattr(compare, "fetch_yahoo", lambda: _bars("2026-10-15"))
    report = tmp_path / "partial.json"
    monkeypatch.setattr(sys, "argv", [
        "compare_nifty_providers.py", "--start", "2026-10-15", "--end", "2026-10-15",
        "--output", str(report),
    ])
    assert compare.main() == 2
    saved = report.read_text()
    assert "TOP_SECRET_ACCESS_TOKEN" not in saved
    assert "RuntimeError" in saved


def test_yahoo_stored_disagreement_uses_yahoo_labels_not_dhan_labels():
    source, _ = compare.audit_bars(
        _bars("2026-10-15"), label="yahoo", start="2026-10-15", end="2026-10-15"
    )
    stored = source.copy()
    stored.loc[20, "low"] -= 12
    r = compare.compare_yahoo_with_stored(source, stored)
    assert r["pair"] == "yahoo_vs_existing_postgres"
    assert r["result"] == "DISAGREEMENT"
    assert r["different_close_count"] == 0
    assert r["different_ohlc_count"] == 1
    assert r["worst_close_differences"][0].get("dhan") is None
    assert "yahoo" in r["worst_close_differences"][0]
    assert "dhan_minutes_not_in_reference" not in r


def test_extreme_open_mismatch_reports_ist_time_and_full_ohlc():
    first, _ = compare.audit_bars(
        _bars("2026-10-15"), label="dhan",
        start="2026-10-15", end="2026-10-15",
    )
    second = first.copy()
    # Preserve valid OHLC while creating an opening price disagreement.
    second.loc[20, "open"] -= 57.4
    second.loc[20, "low"] -= 57.4
    result = compare.compare_bars(
        first, second, label="dhan_vs_yahoo", tolerance=1.0,
    )
    assert result["result"] == "DISAGREEMENT"
    worst = result["worst_ohlc_discrepancies"][0]
    assert worst["timestamp_ist"].startswith("2026-10-15T09:35:00+05:30")
    assert worst["largest_mismatch_field"] in {"open", "low"}
    assert worst["max_abs_difference_points"] == 57.4
    assert worst["primary_ohlc"]["open"] != worst["reference_ohlc"]["open"]


def test_exact_missing_minutes_displayed_without_synthesizing_bars():
    primary, _ = compare.audit_bars(
        _bars("2026-10-15", count=50), label="dhan",
        start="2026-10-15", end="2026-10-15",
    )
    reference = primary.drop(index=range(10, 24)).copy()
    extra = _bars("2026-10-15", count=1)
    extra["timestamp"] = "2026-10-15T10:05:00+05:30"
    reference = pd.concat([reference, extra], ignore_index=True)
    result = compare.compare_bars(primary, reference, label="dhan_vs_yahoo")
    assert result["matched_minutes"] == 36
    assert len(result["only_in_primary_minutes_ist"]) == 14
    assert result["only_in_primary_minutes_ist"][0].startswith("2026-10-15 09:25:00")
    assert len(result["only_in_reference_minutes_ist"]) == 1
    assert result["only_in_reference_minutes_ist"][0].startswith("2026-10-15 10:05:00")
