from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter

router = APIRouter(tags=["market"])

YAHOO_SYMBOLS = {
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "NIFTY_50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "NIFTYBANK": "^NSEBANK",
}


def _market_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace(" ", "").replace("-", "_")
    return YAHOO_SYMBOLS.get(normalized, symbol.upper())


def _fetch_yahoo_chart(symbol: str, *, interval: str = "1m", period: str = "1d") -> dict[str, Any]:
    yahoo_symbol = _market_symbol(symbol)
    params = urlencode({
        "range": period,
        "interval": interval,
        "includePrePost": "false",
    })
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(yahoo_symbol, safe='')}?{params}"
    request = Request(url, headers={"User-Agent": "QuantGrid/1.0"})

    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    result = payload.get("chart", {}).get("result") or []
    if not result:
        error = payload.get("chart", {}).get("error") or "No market data returned"
        raise RuntimeError(str(error))

    return result[0]


def _sample_candles(symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    start = datetime.now(timezone.utc) - timedelta(minutes=limit - 1)
    candles = []

    for index in range(limit):
        open_price = 22440 + index * 3
        candles.append({
            "symbol": symbol.upper(),
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "open": open_price,
            "high": open_price + 8,
            "low": open_price - 6,
            "close": open_price + 4,
            "volume": 1000 + index * 125,
        })

    return candles


def _candles_from_chart(symbol: str, chart: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    timestamps = chart.get("timestamp") or []
    quote_data = (chart.get("indicators", {}).get("quote") or [{}])[0]
    opens = quote_data.get("open") or []
    highs = quote_data.get("high") or []
    lows = quote_data.get("low") or []
    closes = quote_data.get("close") or []
    volumes = quote_data.get("volume") or []
    timezone_name = chart.get("meta", {}).get("timezone", "UTC")

    candles = []
    for index, timestamp in enumerate(timestamps):
        values = [
            opens[index] if index < len(opens) else None,
            highs[index] if index < len(highs) else None,
            lows[index] if index < len(lows) else None,
            closes[index] if index < len(closes) else None,
        ]
        if any(value is None for value in values):
            continue

        candles.append({
            "symbol": symbol.upper(),
            "timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
            "exchange_timezone": timezone_name,
            "open": round(float(values[0]), 2),
            "high": round(float(values[1]), 2),
            "low": round(float(values[2]), 2),
            "close": round(float(values[3]), 2),
            "volume": int(volumes[index] or 0) if index < len(volumes) else 0,
        })

    return candles[-limit:]


@router.get("/price")
def get_price(symbol: str = "NIFTY"):
    try:
        chart = _fetch_yahoo_chart(symbol)
        meta = chart.get("meta", {})
        price = meta.get("regularMarketPrice")
        previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        change_pct = None
        if price is not None and previous_close:
            change_pct = round(((float(price) - float(previous_close)) / float(previous_close)) * 100, 2)

        return {
            "symbol": symbol.upper(),
            "market_symbol": meta.get("symbol", _market_symbol(symbol)),
            "price": round(float(price), 2) if price is not None else None,
            "change_pct": change_pct,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "yahoo-finance",
            "exchange_timezone": meta.get("timezone"),
        }
    except Exception as exc:
        latest = _sample_candles(symbol, limit=1)[-1]
        return {
            "symbol": symbol.upper(),
            "market_symbol": _market_symbol(symbol),
            "price": latest["close"],
            "change_pct": None,
            "timestamp": latest["timestamp"],
            "source": "sample-fallback",
            "warning": f"Live market data unavailable: {exc}",
        }


@router.get("/signals")
def get_signals():
    return {
        "signal": "BUY",
        "confidence": 0.78
    }


@router.get("/candles/{symbol}")
def get_candles(symbol: str, interval: str = "1m", period: str = "1d", limit: int = 100):
    limit = max(1, min(limit, 500))

    try:
        chart = _fetch_yahoo_chart(symbol, interval=interval, period=period)
        candles = _candles_from_chart(symbol, chart, limit=limit)
        if not candles:
            raise RuntimeError("No complete candles returned")

        return {
            "symbol": symbol.upper(),
            "market_symbol": chart.get("meta", {}).get("symbol", _market_symbol(symbol)),
            "interval": interval,
            "period": period,
            "source": "yahoo-finance",
            "candles": candles,
        }
    except Exception as exc:
        return {
            "symbol": symbol.upper(),
            "market_symbol": _market_symbol(symbol),
            "interval": interval,
            "period": period,
            "source": "sample-fallback",
            "warning": f"Live market data unavailable: {exc}",
            "candles": _sample_candles(symbol, limit=min(limit, 100)),
        }
