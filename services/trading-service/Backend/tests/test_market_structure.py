from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Backend.domain.market_structure import analyze_market_structure


def _candles(count: int = 40) -> list[dict[str, float | str]]:
    start = datetime(2026, 5, 22, 3, 45, tzinfo=timezone.utc)
    candles: list[dict[str, float | str]] = []
    price = 23_700.0
    for index in range(count):
        open_price = price
        close = price + 4
        high = close + 3
        low = open_price - 2
        candles.append({
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1_000 + index * 10,
        })
        price = close
    return candles


def test_market_structure_returns_institutional_dashboard_shape():
    analysis = analyze_market_structure(_candles())

    assert analysis["bias"] in {"bullish", "bearish", "range"}
    assert "market_structure" in analysis
    assert "liquidity_analysis" in analysis
    assert "levels" in analysis
    assert "trade_decision" in analysis
    assert isinstance(analysis["reasoning"], list)
