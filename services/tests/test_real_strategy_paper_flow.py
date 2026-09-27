from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone



START = datetime(2026, 5, 29, 9, 15, tzinfo=timezone.utc)


def _candles(values: list[tuple[float, float, float, float, float]], minutes: int) -> list[dict]:
    return [
        {
            "timestamp": (START + timedelta(minutes=index * minutes)).isoformat(),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
        for index, (open_price, high, low, close, volume) in enumerate(values)
    ]


def _h4_uptrend() -> list[dict]:
    values = []
    for index in range(16):
        open_price = 100 + index * 2
        close = open_price + 1.2
        values.append(
            (
                open_price,
                close + 1.0,
                open_price - 0.8 + index * 0.3,
                close,
                1000 + index * 50,
            )
        )
    return _candles(values, 240)


def _h1_demand_pullback() -> list[dict]:
    values = [
        (108 - index, 109 - index, 104 - index, 105 - index, 1000)
        for index in range(8)
    ]
    values.extend(
        [
            (101.5, 103.0, 99.5, 102.8, 1600),
            (102.5, 104.0, 101.8, 103.5, 1800),
        ]
    )
    return _candles(values, 60)


def _m15_bullish_trigger() -> list[dict]:
    values = [
        (
            102 + index * 0.1,
            103 + index * 0.1,
            101.5 + index * 0.1,
            102.4 + index * 0.1,
            1000 + index * 20,
        )
        for index in range(30)
    ]
    values.extend(
        [
            (103.0, 103.4, 100.8, 101.2, 1300),
            (101.1, 104.8, 100.9, 104.5, 2200),
        ]
    )
    return _candles(values, 15)


@dataclass
class PaperResult:
    broker_order_id: str
    status: str = "filled"


class DeterministicPaperBroker:
    def __init__(self) -> None:
        self.orders: list = []

    async def place_order(self, order) -> PaperResult:
        self.orders.append(order)
        return PaperResult(broker_order_id="PAPER-E2E-1")


def test_real_mtfa_signal_validates_and_submits_one_paper_order(monkeypatch):
    import Backend.application.signal_validation as signal_validation
    from Backend.application.order_management import OrderManagementService
    from Backend.domain.models.context import StrategyContext
    from Backend.domain.strategies.mtfa import MTFAConfig, MTFAStrategy

    validate_signals = signal_validation.validate_signals

    m15 = _m15_bullish_trigger()
    strategy = MTFAStrategy(MTFAConfig(min_score=7))
    raw_signals = strategy.run(
        m15,
        StrategyContext(
            symbol="NIFTY",
            capital=100000,
            risk_pct=1,
            rr_ratio=2,
            params={
                "h4_candles": _h4_uptrend(),
                "h1_candles": _h1_demand_pullback(),
                "m15_candles": m15,
            },
        ),
    )

    assert raw_signals
    selected_raw = raw_signals[-1]

    market_validation = type(
        "Validation",
        (),
        {
            "valid": True,
            "valid_for_analysis": True,
            "valid_for_execution": True,
            "market_status": "LIVE MARKET",
        },
    )()
    monkeypatch.setattr(
        signal_validation,
        "validate_live_candle",
        lambda *args, **kwargs: market_validation,
    )
    monkeypatch.setattr(
        signal_validation,
        "get_price",
        lambda symbol: {
            "source": "dhan",
            "price": selected_raw.entry_price,
        },
    )

    validation_candles = list(m15)
    validation_candles[-1] = {
        **validation_candles[-1],
        "timestamp": selected_raw.signal_time.isoformat(),
        "close": selected_raw.entry_price,
    }

    validated, source = validate_signals(
        raw_signals,
        symbol="NIFTY",
        candles=validation_candles,
        candle_source="dhan",
    )

    assert source == "live"
    assert validated
    signal = validated[0]
    assert signal.metadata["strategy_key"] == "mtfa"
    assert signal.metadata["quality"] == "high"
    assert signal.metadata["risk_reward"] >= 1.99

    broker = DeterministicPaperBroker()
    service = OrderManagementService(broker)
    context = {
        "trades_today": 0,
        "daily_pnl": 0,
        "capital_per_trade": 25000,
        "open_positions": 0,
        "market_data_age_seconds": 5,
        "vix": 14,
    }

    result = asyncio.run(service.submit_signal(signal, context))

    assert result.accepted is True
    assert result.status == "filled"
    assert result.broker_order_id == "PAPER-E2E-1"
    assert len(broker.orders) == 1
    assert broker.orders[0].symbol == "NIFTY"
    assert broker.orders[0].side == signal.side
