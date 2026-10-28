from datetime import datetime, timedelta, timezone

from Backend.trading_system.backtesting import BacktestEngine


def make_candles(count=12):
    start = datetime(2026, 10, 20, 9, 15, tzinfo=timezone.utc)

    return [
        {
            "timestamp": (start + timedelta(minutes=i)).isoformat(),
            "open": 100 + i,
            "high": 102 + i,
            "low": 98 + i,
            "close": 101 + i,
            "volume": 1000,
        }
        for i in range(count)
    ]


class RecordingTradingService:
    def __init__(self):
        self.calls = []
        self.first_candle_values = []

    def run_strategy(self, **kwargs):
        records = kwargs["data"]

        self.calls.append(len(records))
        self.first_candle_values.append(records[0]["close"])

        # Deliberately mutate the input.
        records[0]["close"] = -999

        return []


def test_cached_records_have_no_lookahead_and_are_isolated():
    engine = BacktestEngine()
    recorder = RecordingTradingService()
    engine.trading_service = recorder

    result = engine.run(
        candles=make_candles(),
        strategy_name="breakout",
        symbol="NIFTY",
    )

    assert recorder.calls == list(range(1, 13))
    assert recorder.first_candle_values == [101] * 12
    assert result.total_trades == 0


def test_custom_generate_signal_override_is_preserved():
    class CustomEngine(BacktestEngine):
        def __init__(self):
            super().__init__()
            self.calls = []

        def _generate_signal(
            self,
            frame,
            index,
            strategy_name,
            symbol,
            capital,
            risk_pct,
            rr_ratio,
            min_score,
        ):
            self.calls.append(index)
            return None

    engine = CustomEngine()

    engine.run(
        candles=make_candles(),
        strategy_name="breakout",
        symbol="NIFTY",
    )

    assert engine.calls == list(range(12))
