from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_auto_signal_hook_uses_only_supported_dhan_intervals_and_explicit_timeframes():
    hook = (ROOT / "apps/frontend/src/hooks/useAutoSignals.ts").read_text(encoding="utf-8")

    assert 'api.candles("NIFTY", "1d")' not in hook
    assert 'api.candles("NIFTY", "1m", 500)' in hook
    assert 'api.candles("NIFTY", "5m", 500)' in hook
    assert 'api.candles("NIFTY", "15m", 500)' in hook
    assert 'api.candles("NIFTY", "60m", 500)' in hook

    for field in (
        "m5_candles",
        "m15_candles",
        "h1_candles",
        "h4_candles",
        "daily_candles",
    ):
        assert field in hook

    assert "aggregateCandles(h1_candles, 4)" in hook
    assert "aggregateDailyCandles(h1_candles)" in hook


def test_frontend_candle_api_can_request_more_history():
    api = (ROOT / "apps/frontend/src/api/index.ts").read_text(encoding="utf-8")

    assert 'candles: (symbol: string, interval = "5m", limit = 100)' in api
    assert "params: { interval, limit }" in api
