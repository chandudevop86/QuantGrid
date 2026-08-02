from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from conftest import admin_headers


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from Backend.application.volume_analysis import analyze_volume
from app.analysis.delivery_analysis import analyze_delivery
from app.analysis.smart_money import analyze_smart_money
from app.analysis.volume_profile import calculate_volume_profile
from app.models.volume_models import VolumeAnalysisRequest


def _candles(count: int = 60, *, bearish: bool = False) -> list[dict[str, object]]:
    start = datetime(2026, 7, 1, 3, 45, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    price = 22500.0
    for index in range(count):
        drift = -4 if bearish else 4
        open_price = price
        close = price + drift
        volume = 1000 + index * 10
        if index == count - 1:
            close = price - 50 if bearish else price + 50
            volume = 4500
        rows.append(
            {
                "timestamp": (start + timedelta(minutes=index)).isoformat(),
                "open": open_price,
                "high": max(open_price, close) + 5,
                "low": min(open_price, close) - 5,
                "close": close,
                "volume": volume,
            }
        )
        price = close
    return rows


def test_volume_analysis_detects_bullish_breakout_confirmation():
    result = analyze_volume(symbol="NIFTY", timeframe="1m", candles=_candles()).to_dict()

    assert result["symbol"] == "NIFTY"
    assert result["relative_volume"] >= 1.5
    assert result["volume_spike"] is True
    assert result["breakout_confirmation"] is True
    assert result["institutional_buying"] is True
    assert result["signal"] == "BUY"
    assert {"poc", "vah", "val", "hvn", "lvn"} <= set(result["volume_profile"])


def test_volume_analysis_detects_bearish_breakdown_confirmation():
    result = analyze_volume(symbol="NIFTY", timeframe="1m", candles=_candles(bearish=True)).to_dict()

    assert result["breakdown_confirmation"] is True
    assert result["institutional_selling"] is True
    assert result["signal"] == "SELL"
    assert result["smart_money_score"] <= 50


def test_volume_analysis_api_accepts_mock_ohlcv(app_client):
    headers = admin_headers(app_client)

    response = app_client.post(
        "/market/volume-analysis",
        headers=headers,
        json={
            "symbol": "NIFTY",
            "timeframe": "1m",
            "candles": _candles(),
            "delivery_data": [{"delivery_percentage": 62}],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["delivery_percentage"] == 62
    assert payload["signal"] == "BUY"
    assert payload["volume_confidence"] >= 60


def test_app_volume_compatibility_modules_delegate_to_backend_engine():
    candles = _candles()
    request = VolumeAnalysisRequest(symbol="NIFTY", timeframe="1m", candles=candles)
    profile = calculate_volume_profile(request.candles)
    delivery = analyze_delivery([{"delivered_quantity": 620, "traded_quantity": 1000}])
    smart_money = analyze_smart_money(symbol=request.symbol, timeframe=request.timeframe, candles=request.candles)

    assert profile["poc"] is not None
    assert delivery["delivery_percentage"] == 62
    assert delivery["delivery_signal"] == "ACCUMULATION"
    assert smart_money["signal"] == "BUY"
    assert smart_money["smart_money_score"] >= 50
