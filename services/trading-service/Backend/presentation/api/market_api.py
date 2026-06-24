from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, status

from Backend.application.candle_validation import validate_live_candle
from Backend.application.market_data_service import get_market_data_service
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
from Backend.core.config import get_settings
from Backend.infrastructure.broker.dhan_status import dhan_credentials
from Backend.presentation.api.roles import require_roles
from Backend.application.quant_modules import option_chain_engine
from Backend.application.monitoring import observe_option_chain_failure

router = APIRouter(tags=["market"])
logger = logging.getLogger("quantgrid.option_chain")

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


def _provider_status_from_validation(provider: Any, validation: Any | None = None) -> dict[str, Any]:
    latest_fetch_at = getattr(provider, "latest_fetch_at", None)
    fresh = bool(validation and validation.valid_for_analysis)
    return provider.status_payload() | {
        "latest_fetch_at": latest_fetch_at,
        "fresh": fresh,
        "stale": not fresh,
        "validation": validation.model_dump() if validation else None,
    }


def _ensure_live_provider_allowed(source: str) -> None:
    settings = get_settings()
    normalized = str(source or "").strip().lower()
    if settings.live_trading_enabled and normalized in {"yahoo-finance", "yahoo", "demo", "sample", "sample-fallback"} and not settings.allow_yahoo_for_live:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Yahoo/sample market data is paper/demo only. Configure QUANTGRID_MARKET_DATA_PROVIDER=broker for live trading.",
        )


def _validate_live_price_payload(payload: dict[str, Any]) -> None:
    settings = get_settings()
    if not settings.live_trading_enabled:
        return
    source = str(payload.get("source") or "")
    _ensure_live_provider_allowed(source)
    price = payload.get("price")
    if price is None or float(price) <= 0:
        raise RuntimeError("Live market data price is zero or missing.")
    exchange_timezone = str(payload.get("exchange_timezone") or "")
    if exchange_timezone != "Asia/Kolkata":
        raise RuntimeError(f"Live market data timestamp timezone must be Asia/Kolkata; got {exchange_timezone or 'unknown'}.")


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


def _dhan_option_payload(path: str, body: dict[str, Any]) -> dict[str, Any]:
    credentials = dhan_credentials()
    access_token = credentials["access_token"]
    client_id = credentials["client_id"]
    if not access_token or not client_id:
        raise RuntimeError("Dhan client ID or access token is not configured. Open Dhan Login and save valid credentials.")

    request = Request(
        f"https://api.dhan.co/v2/{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "access-token": access_token,
            "client-id": client_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "QuantGrid/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise RuntimeError("Dhan rejected the saved access token. Open Dhan Login and save a fresh token.") from exc
        raise


def _dhan_option_rows(symbol: str, strikes: list[int]) -> tuple[list[dict[str, Any]], str | None]:
    security_id = int(os.getenv(f"DHAN_SECURITY_ID_{symbol.upper()}", "13"))
    exchange_segment = os.getenv("DHAN_MARKET_EXCHANGE_SEGMENT", "IDX_I")
    base_body = {"UnderlyingScrip": security_id, "UnderlyingSeg": exchange_segment}

    expiry_payload = _dhan_option_payload("optionchain/expirylist", base_body)
    expiry_values = expiry_payload.get("data") or expiry_payload.get("expiry") or expiry_payload.get("expiryList") or []
    expiry = next((str(item) for item in expiry_values if item), None)
    if not expiry:
        raise RuntimeError("Dhan did not return an option-chain expiry.")

    chain_payload = _dhan_option_payload("optionchain", base_body | {"Expiry": expiry})
    option_chain = chain_payload.get("data", {}).get("oc") or chain_payload.get("oc") or {}

    rows = []
    for strike in strikes:
        strike_payload = option_chain.get(str(strike)) or option_chain.get(f"{float(strike):.6f}") or {}
        call = strike_payload.get("ce") or strike_payload.get("CE") or {}
        put = strike_payload.get("pe") or strike_payload.get("PE") or {}
        rows.append({
            "strike": strike,
            "ce": {
                "ltp": call.get("last_price") or call.get("ltp"),
                "change": call.get("change") or call.get("net_change"),
                "volume": call.get("volume"),
                "oi": call.get("oi") or call.get("open_interest"),
                "iv": call.get("implied_volatility") or call.get("iv"),
            },
            "pe": {
                "ltp": put.get("last_price") or put.get("ltp"),
                "change": put.get("change") or put.get("net_change"),
                "volume": put.get("volume"),
                "oi": put.get("oi") or put.get("open_interest"),
                "iv": put.get("implied_volatility") or put.get("iv"),
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


def _fallback_option_chain(symbol: str, *, strikes_each_side: int, step: int, warning: str) -> dict[str, Any]:
    payload = option_chain_engine(symbol, strikes_each_side=strikes_each_side, step=step)
    return {
        "symbol": payload["symbol"],
        "underlying_price": payload["underlying_price"],
        "spot": payload["underlying_price"],
        "atm_strike": payload["atm_strike"],
        "ATM": payload["atm_strike"],
        "atm": payload["atm_strike"],
        "step": payload["step"],
        "expiry": payload["expiry"],
        "source": payload["source"],
        "warning": warning,
        "updated_at": payload["updated_at"],
        "rows": payload["rows"],
        "pcr": payload.get("pcr"),
        "PCR": payload.get("pcr"),
        "max_pain": payload.get("max_pain"),
        "support": payload.get("support"),
        "resistance": payload.get("resistance"),
        "signals": {
            "bias": "NEUTRAL",
            "reason": warning,
            "total_call_oi": int(sum(float(row["ce"].get("oi") or 0) for row in payload["rows"])),
            "total_put_oi": int(sum(float(row["pe"].get("oi") or 0) for row in payload["rows"])),
            "pcr": payload.get("pcr"),
            "atm_strike": payload["atm_strike"],
            "max_pain": payload.get("max_pain"),
        },
    }


@router.get("/price")
def get_price(
    symbol: str = "NIFTY",
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    return get_ltp(symbol, _role=_role)


@router.get("/ltp/{symbol}")
def get_ltp(
    symbol: str,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    try:
        settings = get_settings()
        service = get_market_data_service()
        payload = service.get_ltp(symbol, mode="live" if settings.live_trading_enabled else "paper")
        _ensure_live_provider_allowed(str(payload.get("provider")))
        price = payload.get("ltp", payload.get("price"))
        meta_symbol = payload.get("market_symbol", _market_symbol(symbol))
        change_pct = None
        if "change_pct" in payload:
            change_pct = payload.get("change_pct")

        payload = {
            **payload,
            "symbol": symbol.upper(),
            "market_symbol": meta_symbol,
            "ltp": round(float(price), 2) if price is not None else None,
            "price": round(float(price), 2) if price is not None else None,
            "change_pct": change_pct,
            "timestamp": payload.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "provider_warning": payload.get("provider_warning"),
        }
        if payload["price"] is None or float(payload["price"]) <= 0:
            raise RuntimeError("Market provider returned zero or missing price")
        _validate_live_price_payload(payload)
        store_price_tick(payload)
        return payload
    except Exception as exc:
        if get_settings().live_trading_enabled:
            raise _market_data_unavailable(exc) from exc
        cached = latest_price_tick(symbol)
        if cached:
            cached["warning"] = "Live market data provider is unavailable; served latest stored live price."
            return cached
        if not _allow_sample_market_data():
            raise _market_data_unavailable(exc) from exc
        latest = _sample_candles(symbol, limit=1)[-1]
        return {
            "provider": "sample",
            "symbol": symbol.upper(),
            "market_symbol": _market_symbol(symbol),
            "ltp": latest["close"],
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
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    strikes_each_side = max(1, min(int(strikes_each_side), 10))
    step = max(1, int(step))
    try:
        price_payload = get_price(symbol, _role=_role)
        price = float(price_payload.get("price") or 0.0)
    except Exception as exc:
        logger.exception("option_chain_price_fetch_failed", extra={"symbol": symbol, "error_type": exc.__class__.__name__})
        observe_option_chain_failure("market-price", exc.__class__.__name__)
        if get_settings().live_trading_enabled:
            return _fallback_option_chain(
                symbol,
                strikes_each_side=strikes_each_side,
                step=step,
                warning=f"Live market price unavailable: {exc}. Showing synthetic option-chain fallback.",
            )
        return _fallback_option_chain(
            symbol,
            strikes_each_side=strikes_each_side,
            step=step,
            warning=f"Live market price unavailable: {exc}. Showing synthetic option-chain fallback.",
        )
    if price <= 0:
        if get_settings().live_trading_enabled:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Current market price is unavailable.")
        return _fallback_option_chain(
            symbol,
            strikes_each_side=strikes_each_side,
            step=step,
            warning="Current market price is unavailable. Showing synthetic option-chain fallback.",
        )

    atm = _nearest_strike(price, step)
    strikes = [atm + (offset * step) for offset in range(-strikes_each_side, strikes_each_side + 1)]
    source = "derived-from-underlying"
    expiry = None
    warning = "Live option-chain provider unavailable; showing ATM strike ladder from current NIFTY price."

    try:
        rows, expiry = _dhan_option_rows(symbol, strikes)
        if any(row["ce"].get("ltp") is not None or row["pe"].get("ltp") is not None for row in rows):
            source = "dhan-option-chain"
            warning = None
        else:
            rows = _derived_option_rows(strikes)
            warning = "Dhan option-chain returned no matching strikes; showing ATM strike ladder from current NIFTY price."
    except Exception as dhan_exc:
        logger.exception("option_chain_provider_fetch_failed", extra={"symbol": symbol, "provider": "dhan", "error_type": dhan_exc.__class__.__name__})
        observe_option_chain_failure("dhan", dhan_exc.__class__.__name__)
        try:
            rows, expiry = _yahoo_option_rows(symbol, strikes)
        except Exception as yahoo_exc:
            logger.exception("option_chain_provider_fetch_failed", extra={"symbol": symbol, "provider": "yahoo", "error_type": yahoo_exc.__class__.__name__})
            observe_option_chain_failure("yahoo", yahoo_exc.__class__.__name__)
            rows = _derived_option_rows(strikes)
            warning = f"Live option-chain provider unavailable: {dhan_exc}. Showing ATM strike ladder from current NIFTY price."
        else:
            if any(row["ce"].get("ltp") is not None or row["pe"].get("ltp") is not None for row in rows):
                source = "yahoo-finance-options"
                warning = f"Dhan option-chain unavailable: {dhan_exc}. Showing Yahoo option-chain data."
            else:
                rows = _derived_option_rows(strikes)
                warning = f"Live option-chain provider unavailable: {dhan_exc}. Showing ATM strike ladder from current NIFTY price."

    call_oi = sum(float(row["ce"].get("oi") or 0) for row in rows)
    put_oi = sum(float(row["pe"].get("oi") or 0) for row in rows)
    pcr = round(put_oi / call_oi, 3) if call_oi else 0.0
    support_rows = [row for row in rows if row["strike"] < atm]
    resistance_rows = [row for row in rows if row["strike"] > atm]
    support = max(support_rows, key=lambda row: float(row["pe"].get("oi") or 0))["strike"] if support_rows else atm
    resistance = max(resistance_rows, key=lambda row: float(row["ce"].get("oi") or 0))["strike"] if resistance_rows else atm
    return {
        "symbol": symbol.upper(),
        "underlying_price": round(price, 2),
        "spot": round(price, 2),
        "atm_strike": atm,
        "ATM": atm,
        "atm": atm,
        "step": step,
        "expiry": expiry,
        "source": source,
        "warning": warning,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "pcr": pcr,
        "PCR": pcr,
        "max_pain": atm,
        "support": support,
        "resistance": resistance,
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
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    limit = max(1, min(limit, 500))

    try:
        settings = get_settings()
        service = get_market_data_service()
        service_payload = service.get_candles(
            symbol,
            interval,
            period,
            limit,
            mode="live" if settings.live_trading_enabled else "paper",
        )
        candles = list(service_payload.get("candles", []))
        source = service_payload.get("provider_name") or service_payload.get("provider")
        _ensure_live_provider_allowed(str(source))
        market_symbol = _market_symbol(symbol)
        provider_fetched_at = service_payload.get("latest_fetch_at") or service_payload.get("fetched_at") or datetime.now(timezone.utc).isoformat()
        validation = validate_live_candle(
            candles,
            interval=interval,
            mode="live" if settings.live_trading_enabled else "paper",
            source=source,
            provider_fetched_at=provider_fetched_at,
        )
        if settings.live_trading_enabled and not validation.valid_for_execution:
            raise RuntimeError(f"Live market data failed validation: {validation.market_status}")

        payload = {
            "symbol": symbol.upper(),
            "market_symbol": market_symbol,
            "interval": interval,
            "period": period,
            "source": source,
            "volume_status": _volume_status(market_symbol, candles),
            "provider_warning": service_payload.get("provider_warning"),
            "fetched_at": provider_fetched_at,
            "cache_status": service_payload.get("cache_status"),
            "feed_delay_seconds": service_payload.get("feed_delay_seconds"),
            "candles": candles,
            "validation": validation.model_dump(),
        }
        store_candles(
            symbol=symbol,
            market_symbol=market_symbol,
            interval=interval,
            source=source,
            candles=candles,
        )
        return payload
    except Exception as exc:
        if get_settings().live_trading_enabled:
            raise _market_data_unavailable(exc) from exc
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
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
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
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
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
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
):
    return market_data_summary(symbol, interval)


@router.get("/provider/status")
def get_market_provider_status(
    symbol: str = "NIFTY",
    interval: str = "1m",
    limit: int = 100,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
):
    payload = get_market_data_service().health(symbol=symbol, interval=interval)
    suitability = "live" if payload.get("live_suitable") else "paper"
    return {
        **payload,
        "suitability": suitability,
        "latest_fetch_time": payload.get("latest_fetch_at"),
        "freshness": "fresh" if payload.get("fresh") else "stale",
    }


@router.get("/feed/health")
def get_market_feed_health(
    symbol: str = "NIFTY",
    interval: str = "1m",
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
):
    return get_market_data_service().health(symbol=symbol, interval=interval)
