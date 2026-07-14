from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, status

app = FastAPI(title="QuantGrid Market Data Service")

YAHOO_SYMBOLS = {
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "NIFTY_50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "NIFTYBANK": "^NSEBANK",
}


def market_data_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Live market data unavailable: {exc}",
    )


def market_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace(" ", "").replace("-", "_")
    return YAHOO_SYMBOLS.get(normalized, symbol.upper())


def fetch_yahoo_chart(symbol: str, *, interval: str = "1m", period: str = "1d") -> dict[str, Any]:
    yahoo_symbol = market_symbol(symbol)
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


def candles_from_chart(symbol: str, chart: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    timestamps = chart.get("timestamp") or []
    quote_data = (chart.get("indicators", {}).get("quote") or [{}])[0]
    opens = quote_data.get("open") or []
    highs = quote_data.get("high") or []
    lows = quote_data.get("low") or []
    closes = quote_data.get("close") or []
    volumes = quote_data.get("volume") or []

    rows = []
    for index, timestamp in enumerate(timestamps):
        values = [
            opens[index] if index < len(opens) else None,
            highs[index] if index < len(highs) else None,
            lows[index] if index < len(lows) else None,
            closes[index] if index < len(closes) else None,
        ]
        if any(value is None for value in values):
            continue

        rows.append({
            "symbol": symbol.upper(),
            "timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
            "exchange_timezone": chart.get("meta", {}).get("timezone", "UTC"),
            "open": round(float(values[0]), 2),
            "high": round(float(values[1]), 2),
            "low": round(float(values[2]), 2),
            "close": round(float(values[3]), 2),
            "volume": int(volumes[index] or 0) if index < len(volumes) else 0,
        })

    return rows[-limit:]


def volume_status(market_symbol: str, rows: list[dict[str, Any]]) -> str:
    if market_symbol.startswith("^") and rows and all(int(row.get("volume") or 0) == 0 for row in rows):
        return "not_reported_for_index"

    return "reported"


@app.get("/health")
def health():
    return {"status": "ok", "service": "market-data"}


@app.get("/price/{symbol}")
def price(symbol: str):
    try:
        chart = fetch_yahoo_chart(symbol)
        meta = chart.get("meta", {})
        price_value = meta.get("regularMarketPrice")
        previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        change_pct = None
        if price_value is not None and previous_close:
            change_pct = round(((float(price_value) - float(previous_close)) / float(previous_close)) * 100, 2)

        return {
            "symbol": symbol.upper(),
            "market_symbol": meta.get("symbol", market_symbol(symbol)),
            "price": round(float(price_value), 2) if price_value is not None else None,
            "change_pct": change_pct,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "yahoo-finance",
            "exchange_timezone": meta.get("timezone"),
        }
    except Exception as exc:
        raise market_data_unavailable(exc) from exc


@app.get("/candles/{symbol}")
def candles(symbol: str, interval: str = "1m", period: str = "1d", limit: int = 100):
    limit = max(1, min(limit, 200))

    try:
        chart = fetch_yahoo_chart(symbol, interval=interval, period=period)
        rows = candles_from_chart(symbol, chart, limit=limit)
        if not rows:
            raise RuntimeError("No complete candles returned")
        yahoo_symbol = chart.get("meta", {}).get("symbol", market_symbol(symbol))

        return {
            "symbol": symbol.upper(),
            "market_symbol": yahoo_symbol,
            "interval": interval,
            "period": period,
            "source": "yahoo-finance",
            "volume_status": volume_status(yahoo_symbol, rows),
            "candles": rows,
        }
    except Exception as exc:
        raise market_data_unavailable(exc) from exc
