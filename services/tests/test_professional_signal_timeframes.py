from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_professional_signal_paths_use_real_hourly_h4_and_daily_timeframes():
    source = (
        ROOT
        / "services/trading-service/Backend/presentation/api/professional_api.py"
    ).read_text(encoding="utf-8")

    assert 'interval="60m"' in source
    assert '"h1_candles": hourly' in source
    assert '"h4_candles": h4_candles' in source
    assert '"daily_candles": daily_candles' in source
    assert '"htf_candles": hourly' in source

    assert '"h1_candles": fifteen_minute' not in source
    assert '"h4_candles": fifteen_minute' not in source
    assert '"daily_candles": fifteen_minute' not in source


def test_signal_audit_exposes_hourly_source_and_multi_timeframe_split():
    source = (
        ROOT
        / "services/trading-service/Backend/presentation/api/professional_api.py"
    ).read_text(encoding="utf-8")

    assert '"hourly_source": hourly_response.get("source")' in source
    assert '"1h": hourly' in source
    assert '"4h": h4_candles' in source
    assert '"1d": daily_candles' in source
