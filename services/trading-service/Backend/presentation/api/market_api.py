from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, status

from Backend.application.candle_validation import validate_live_candle
from Backend.application.market_data_store import (
    latest_candles,
    latest_price_tick,
    market_data_summary,
    store_candles,
    store_price_tick,
)
from Backend.infrastructure.data.market_data_provider import (
    YAHOO_TRADING_GRADE_WARNING,
    get_market_data_provider,
    market_symbol,
)
from Backend.presentation.api.roles import require_roles

router = APIRouter(tags=["market"])

def _allow_sample_market_data() -> bool:
    return os.getenv("ALLOW_SAMPLE_MARKET_DATA", "false").strip().lower() in {"1", "true", "yes"}


def _market_data_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Live market data unavailable: {exc}",
    )


def _stored_candle_response(symbol: str, interval: str, period: str, limit: int) -> dict[str, Any] | None:
    candles = latest_candles(symbol, interval, limit)
    if not candles:
        return None

    return {
        "symbol": symbol.upper(),
        "market_symbol": _market_symbol(symbol),
        "interval": interval,
        "period": period,
        "source": "stored-live-cache",
        "volume_status": _volume_status(_market_symbol(symbol), candles),
        "candles": candles,
        "cached": True,
        "warning": "Live market data provider is unavailable; served latest stored live candles.",
    }


def _market_symbol(symbol: str) -> str:
    return market_symbol(symbol)


def _fetch_yahoo_chart(symbol: str, *, interval: str = "1m", period: str = "1d") -> dict[str, Any]:
    return get_market_data_provider().fetch_chart(symbol, interval=interval, period=period)


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
    timezone_name = chart.get("meta", {}).get("timezone", "Asia/Kolkata")

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


def _volume_status(market_symbol: str, candles: list[dict[str, Any]]) -> str:
    if market_symbol.startswith("^") and candles and all(int(candle.get("volume") or 0) == 0 for candle in candles):
        return "not_reported_for_index"

    return "reported"


def _nearest_strike(price: float, step: int = 50) -> int:
    return int(round(float(price) / step) * step) if price > 0 else 0


def _expiry_from_timestamp(timestamp: int | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(int(timestamp), timezone.utc).date().isoformat()


def _yahoo_option_rows(symbol: str, strikes: list[int]) -> tuple[list[dict[str, Any]], str | None]:
    yahoo_symbol = _market_symbol(symbol)
    url = f"https://query2.finance.yahoo.com/v7/finance/options/{quote(yahoo_symbol, safe='')}"
    request = Request(url, headers={"User-Agent": "QuantGrid/1.0"})
    with urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))

    result = (payload.get("optionChain", {}).get("result") or [{}])[0]
    options = (result.get("options") or [{}])[0]
    expiry = _expiry_from_timestamp(options.get("expirationDate"))
    calls = {int(round(float(item.get("strike")))): item for item in options.get("calls", []) if item.get("strike") is not None}
    puts = {int(round(float(item.get("strike")))): item for item in options.get("puts", []) if item.get("strike") is not None}

    rows = []
    for strike in strikes:
        call = calls.get(strike, {})
        put = puts.get(strike, {})
        rows.append({
            "strike": strike,
            "ce": {
                "ltp": call.get("lastPrice"),
                "change": call.get("change"),
                "volume": call.get("volume"),
                "oi": call.get("openInterest"),
                "iv": call.get("impliedVolatility"),
            },
            "pe": {
                "ltp": put.get("lastPrice"),
                "change": put.get("change"),
                "volume": put.get("volume"),
                "oi": put.get("openInterest"),
                "iv": put.get("impliedVolatility"),
            },
        })
    return rows, expiry


def _derived_option_rows(strikes: list[int]) -> list[dict[str, Any]]:
    return [
        {
            "strike": strike,
            "ce": {"ltp": None, "change": None, "volume": None, "oi": None, "iv": None},
            "pe": {"ltp": None, "change": None, "volume": None, "oi": None, "iv": None},
        }
        for strike in strikes
    ]


@router.get("/price")
def get_price(
    symbol: str = "NIFTY",
    _role: str = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    try:
        chart = _fetch_yahoo_chart(symbol)
        meta = chart.get("meta", {})
        price = meta.get("regularMarketPrice")
        previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        change_pct = None
        if price is not None and previous_close:
            change_pct = round(((float(price) - float(previous_close)) / float(previous_close)) * 100, 2)

        payload = {
            "symbol": symbol.upper(),
            "market_symbol": meta.get("symbol", _market_symbol(symbol)),
            "price": round(float(price), 2) if price is not None else None,
            "change_pct": change_pct,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "yahoo-finance",
            "exchange_timezone": meta.get("timezone"),
            "provider_latency_ms": chart.get("provider_latency_ms"),
            "provider_warning": YAHOO_TRADING_GRADE_WARNING,
        }
        store_price_tick(payload)
        return payload
    except Exception as exc:
        cached = latest_price_tick(symbol)
        if cached:
            cached["warning"] = "Live market data provider is unavailable; served latest stored live price."
            return cached
        if not _allow_sample_market_data():
            raise _market_data_unavailable(exc) from exc
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


@router.get("/option-chain/{symbol}")
def get_option_chain(
    symbol: str,
    strikes_each_side: int = 5,
    step: int = 50,
    _role: str = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    price_payload = get_price(symbol, _role=_role)
    price = float(price_payload.get("price") or 0.0)
    if price <= 0:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Current market price is unavailable.")

    strikes_each_side = max(1, min(int(strikes_each_side), 10))
    step = max(1, int(step))
    atm = _nearest_strike(price, step)
    strikes = [atm + (offset * step) for offset in range(-strikes_each_side, strikes_each_side + 1)]
    source = "derived-from-underlying"
    expiry = None
    warning = "Live option-chain provider unavailable; showing ATM strike ladder from current NIFTY price."

    try:
        rows, expiry = _yahoo_option_rows(symbol, strikes)
        if any(row["ce"].get("ltp") is not None or row["pe"].get("ltp") is not None for row in rows):
            source = "yahoo-finance-options"
            warning = YAHOO_TRADING_GRADE_WARNING
        else:
            rows = _derived_option_rows(strikes)
    except Exception as exc:
        rows = _derived_option_rows(strikes)
        warning = f"Live option-chain provider unavailable: {exc}. Showing ATM strike ladder from current NIFTY price."

    return {
        "symbol": symbol.upper(),
        "underlying_price": round(price, 2),
        "atm_strike": atm,
        "step": step,
        "expiry": expiry,
        "source": source,
        "warning": warning,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    }


@router.get("/signals")
def get_signals():
    return {"signals": []}


@router.get("/candles/{symbol}")
def get_candles(
    symbol: str,
    interval: str = "1m",
    period: str = "1d",
    limit: int = 100,
    _role: str = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    limit = max(1, min(limit, 500))

    try:
        chart = _fetch_yahoo_chart(symbol, interval=interval, period=period)
        candles = _candles_from_chart(symbol, chart, limit=limit)
        if not candles:
            raise RuntimeError("No complete candles returned")
        market_symbol = chart.get("meta", {}).get("symbol", _market_symbol(symbol))

        payload = {
            "symbol": symbol.upper(),
            "market_symbol": market_symbol,
            "interval": interval,
            "period": period,
            "source": "yahoo-finance",
            "volume_status": _volume_status(market_symbol, candles),
            "provider_warning": YAHOO_TRADING_GRADE_WARNING,
            "provider_latency_ms": chart.get("provider_latency_ms"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "candles": candles,
            "validation": validate_live_candle(
                candles,
                interval=interval,
                mode="paper",
                source="yahoo-finance",
                provider_fetched_at=datetime.now(timezone.utc),
            ).model_dump(),
        }
        store_candles(
            symbol=symbol,
            market_symbol=market_symbol,
            interval=interval,
            source="yahoo-finance",
            candles=candles,
        )
        return payload
    except Exception as exc:
        cached = _stored_candle_response(symbol, interval, period, limit)
        if cached:
            return cached
        if not _allow_sample_market_data():
            raise _market_data_unavailable(exc) from exc
        return {
            "symbol": symbol.upper(),
            "market_symbol": _market_symbol(symbol),
            "interval": interval,
            "period": period,
            "source": "sample-fallback",
            "volume_status": "reported",
            "warning": f"Live market data unavailable: {exc}",
            "candles": _sample_candles(symbol, limit=min(limit, 100)),
            "validation": validate_live_candle(_sample_candles(symbol, limit=min(limit, 100)), interval=interval, source="sample-fallback").model_dump(),
        }


@router.get("/validation/{symbol}")
def get_candle_validation(
    symbol: str,
    interval: str = "1m",
    period: str = "1d",
    limit: int = 100,
    mode: str = "paper",
    _role: str = Depends(require_roles("admin", "trader", "analyst", "viewer", "ops")),
):
    response = get_candles(symbol, interval=interval, period=period, limit=limit)
    validation = validate_live_candle(
        list(response.get("candles", [])),
        interval=interval,
        mode=mode if mode in {"live", "paper", "backtest"} else "paper",
        source=response.get("source"),
        provider_fetched_at=response.get("fetched_at"),
    )
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "source": response.get("source"),
        **validation.model_dump(),
    }


@router.get("/stored/{symbol}")
def get_stored_candles(
    symbol: str,
    interval: str = "1m",
    limit: int = 100,
    _role: str = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    limit = max(1, min(limit, 500))
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "source": "stored-live-cache",
        "candles": latest_candles(symbol, interval, limit),
    }


@router.get("/store/status")
def get_market_store_status(
    symbol: str = "NIFTY",
    interval: str = "1m",
    _role: str = Depends(require_roles("admin", "trader", "analyst", "viewer", "ops")),
):
    return market_data_summary(symbol, interval)
