from __future__ import annotations

import json
import logging
import os
import hashlib
import math
import re
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any,Protocol
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import APIRouter, Body, Depends, HTTPException, status

from Backend.infrastructure.http_safety import require_https_url

from Backend.application.candle_validation import validate_live_candle
from Backend.application.redis_service import redis_service
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
from Backend.infrastructure.market_data.dhan_sdk import DhanSdkUnavailable, dhan_sdk_client
from Backend.infrastructure.market_data.dhan_provider import _normalize_candles
from Backend.presentation.api.roles import require_roles
from Backend.application.monitoring import observe_option_chain_failure
from Backend.application.volume_analysis import analyze_volume
from Backend.application.subscriptions import require_entitlement
from app.validation.data_quality import validate_candles, validate_option_chain_rows
# Backend/domain/market_data/provider.py


router = APIRouter(tags=["market"])
logger = logging.getLogger("quantgrid.option_chain")
market_service = get_market_data_service()

_LATEST_OPTION_CONTEXT: dict[str, dict[str, dict[str, Any]]] = {}
_DHAN_OPTION_LOCK = threading.Lock()
_DHAN_OPTION_CACHE: dict[tuple[Any, ...], tuple[float, list[dict[str, Any]], str | None]] = {}
_DHAN_OPTION_COOLDOWN_UNTIL = 0.0
_DHAN_OPTION_COOLDOWN_NAME = "dhan-option-chain"
_DHAN_OPTION_FETCH_LOCK_NAME = "dhan-option-chain-fetch"


def latest_verified_option_context(symbol: str = "NIFTY") -> dict[str, dict[str, Any]]:
    """Return the latest provider observation already validated by this module."""
    return dict(_LATEST_OPTION_CONTEXT.get(symbol.upper(), {}))

DHAN_UNDERLYING_DEFAULTS: dict[str, tuple[int, str]] = {
    "NIFTY": (13, "IDX_I"),
    "BANKNIFTY": (25, "IDX_I"),
    "FINNIFTY": (27, "IDX_I"),
}


def _market_data_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Live market data unavailable: {exc}",
    )


def _stored_candle_response(symbol: str, interval: str, period: str, limit: int) -> dict[str, Any] | None:
    candles = latest_candles(symbol, interval, limit)
    if not candles:
        return None
    valid_candles, data_quality = validate_candles(candles, source="stored-live-cache")

    result = {
        "symbol": symbol.upper(),
        "market_symbol": _market_symbol(symbol),
        "interval": interval,
        "period": period,
        "source": "stored-live-cache",
        "volume_status": _volume_status(_market_symbol(symbol), candles),
        "candles": valid_candles,
        "data_quality": data_quality.model_dump(),
        "cached": True,
        "warning": "Live market data provider is unavailable; served latest stored live candles.",
    }
    return result


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
    url = require_https_url(
        f"https://query2.finance.yahoo.com/v7/finance/options/{quote(yahoo_symbol, safe='')}",
        allowed_hosts={"query2.finance.yahoo.com"},
    )
    request = Request(url, headers={"User-Agent": "QuantGrid/1.0"})
    with urlopen(request, timeout=8) as response:  # nosec B310
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


def _dhan_profile_client_id(access_token: str, timeout: float = 8.0) -> str | None:
    """Fetch the dhanClientId Dhan's own /v2/profile reports for this access token.

    Used only to cross-check against the locally configured client_id (see
    _dhan_option_payload) -- profile itself never sends a client-id header, so it can
    succeed even when the configured DHAN_CLIENT_ID/QUANTGRID_BROKER_CLIENT_ID is stale or
    belongs to a different account than the token. Option-chain DOES send client-id (both as
    a header and in the body), so that mismatch surfaces there as a 401 even though profile
    looked fine.
    """
    profile_url = require_https_url("https://api.dhan.co/v2/profile", allowed_hosts={"api.dhan.co"})
    request = Request(
        profile_url,
        headers={"access-token": access_token, "Accept": "application/json", "User-Agent": "QuantGrid/1.0"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    client_id = payload.get("dhanClientId")
    return str(client_id) if client_id else None


def _dhan_option_payload(path: str, body: dict[str, Any]) -> dict[str, Any]:
    credentials = dhan_credentials()
    access_token = credentials["access_token"]
    client_id = credentials["client_id"]
    if not access_token or not client_id:
        raise RuntimeError("Dhan client ID or access token is not configured. Open Dhan Login and save valid credentials.")

    profile_client_id = _dhan_profile_client_id(access_token)
    if profile_client_id and profile_client_id != str(client_id):
        raise RuntimeError(
            f"Configured Dhan client ID ({client_id}) does not match the account this access "
            f"token actually belongs to (Dhan reports dhanClientId={profile_client_id}). This "
            "is why profile can succeed (it doesn't check client-id) while option-chain fails "
            "with 401 (it does). Update DHAN_CLIENT_ID / QUANTGRID_BROKER_CLIENT_ID to "
            f"{profile_client_id} and retry."
        )

    payload = dict(body)
    payload.setdefault("dhanClientId", client_id)
    option_url = require_https_url(f"https://api.dhan.co/v2/{path}", allowed_hosts={"api.dhan.co"})
    request = Request(
        option_url,
        data=json.dumps(payload).encode("utf-8"),
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
        with urlopen(request, timeout=8) as response:  # nosec B310
            return _ensure_dhan_success(json.loads(response.read().decode("utf-8")))
    except HTTPError as exc:
        detail = _dhan_http_error_detail(exc)
        if exc.code in {401, 403}:
            # A valid, non-expired access token can still get 401/403 specifically on Option
            # Chain: Dhan splits "Trading APIs" (free, what /v2/profile uses) from "Data APIs"
            # (paid add-on subscription, required for Option Chain) -- so "profile works but
            # option-chain doesn't" is consistent with the account simply not having an
            # active Data API subscription, not necessarily a bad/expired token. A newer,
            # separate cause (SEBI-mandated static IP whitelisting, enforced from April 2026)
            # can also 401 requests from an unregistered server IP. The client-id mismatch
            # check above already ruled out the third common cause. Surface all of them
            # rather than just telling the operator to regenerate a token that may be fine.
            hint = (
                "Dhan rejected this request (HTTP {code}). The configured client ID matches "
                "this token's account (ruled out via profile cross-check), so if your Dhan "
                "login/profile check succeeds but this still fails, the most likely causes "
                "are: (a) your account does not have an active Data API subscription (Option "
                "Chain is a paid Data API, separate from free Trading APIs -- check "
                "web.dhan.co > Profile > DhanHQ Trading APIs > Data APIs tab, and note a "
                "just-activated subscription can take a short time to propagate), or "
                "(b) this server's outbound IP is not whitelisted with Dhan (required since "
                "the SEBI static-IP mandate). Dhan's response: {detail}"
            ).format(code=exc.code, detail=detail or "(no additional detail returned)")
            raise RuntimeError(hint) from exc
        raise RuntimeError(detail or f"Dhan option-chain API failed with HTTP {exc.code}.") from exc


def _dhan_http_error_detail(exc: HTTPError) -> str | None:
    try:
        raw_body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    try:
        payload = json.loads(raw_body)
    except (ValueError, json.JSONDecodeError):
        # Not JSON -- still surface whatever Dhan actually sent instead of discarding it.
        # A generic "HTTP 401" with no body tells the operator nothing about WHICH of
        # several distinct 401 causes this is (expired token vs missing Data API
        # subscription vs IP not whitelisted vs wrong client-id) -- the raw body is the only
        # diagnostic signal available at this point.
        snippet = raw_body.strip()[:300]
        return f"Dhan option-chain API failed with HTTP {exc.code}: {snippet}" if snippet else None

    message = _dhan_failure_message(payload)
    if message:
        return message
    # Parsed as JSON but didn't match any known error shape -- still better to show the raw
    # payload than to hide it behind a generic "HTTP 401" message.
    snippet = json.dumps(payload)[:300]
    return f"Dhan option-chain API failed with HTTP {exc.code}: {snippet}"


def _dhan_failure_message(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    remarks = payload.get("remarks")
    if isinstance(remarks, dict):
        message = remarks.get("error_message") or remarks.get("errorMessage") or remarks.get("message")
        code = remarks.get("error_code") or remarks.get("errorCode")
        if message and code:
            return f"Dhan option-chain API rejected the request ({code}): {message}"
        if message:
            return f"Dhan option-chain API rejected the request: {message}"
        if remarks and all(value in {None, ""} for value in remarks.values()):
            return (
                "Dhan option-chain API rejected the request without an error message. "
                "Profile login can still pass in this state; verify that Dhan Data APIs / "
                "Option Chain are enabled for this account and that this server's outbound "
                f"IP is whitelisted. Raw remarks: {json.dumps(remarks)}"
            )
    if isinstance(remarks, str) and remarks:
        return f"Dhan option-chain API rejected the request: {remarks}"
    message = payload.get("errorMessage") or payload.get("error_message") or payload.get("message")
    code = payload.get("errorCode") or payload.get("error_code")
    if message and code:
        return f"Dhan option-chain API rejected the request ({code}): {message}"
    if message:
        return f"Dhan option-chain API rejected the request: {message}"
    data = payload.get("data")
    if isinstance(data, dict):
        provider_errors = [
            (str(error_code), str(error_message).strip())
            for error_code, error_message in data.items()
            if error_message not in {None, ""} and not isinstance(error_message, (dict, list))
        ]
        if provider_errors:
            details = "; ".join(f"{error_code}: {error_message}" for error_code, error_message in provider_errors)
            return f"Dhan option-chain API rejected the request ({details})"
    # None of the known key shapes matched -- rather than silently discarding the payload
    # (which is exactly what produced the unhelpful "rejected the request." generic message
    # before), show the raw payload so the actual reason is visible.
    other_keys = {k: v for k, v in payload.items() if k not in {"status", "data"}}
    if other_keys:
        return f"Dhan option-chain API rejected the request: {json.dumps(other_keys)[:300]}"
    return None


def _option_chain_diagnostics(message: str | None, *, provider: str = "dhan") -> dict[str, Any]:
    text = str(message or "")
    lower = text.lower()
    likely_causes: list[str] = []
    suggested_actions: list[str] = []
    code = "provider_unavailable"

    retry_match = re.search(r"retry after (\d+) seconds", lower)
    retry_after_seconds = int(retry_match.group(1)) if retry_match else None

    if "429" in lower or "too many requests" in lower or "cooldown" in lower:
        code = "dhan_rate_limited"
        likely_causes = ["Dhan Option Chain request frequency exceeded the provider limit."]
        suggested_actions = [
            "Do not repeatedly refresh Option Chain while cooldown is active.",
            "Wait for the displayed cooldown to expire; QuantGrid will retry automatically.",
        ]
    elif "without an error message" in lower or "raw remarks" in lower:
        code = "dhan_data_api_or_ip_whitelist"
        likely_causes = [
            "Dhan profile login can be valid while Option Chain/Data API access is not enabled.",
            "Dhan may be rejecting this server because the outbound/static IP is not whitelisted.",
            "A newly enabled Dhan Data API subscription may not have propagated yet.",
        ]
        suggested_actions = [
            "Open Dhan web console and confirm Data APIs / Option Chain are enabled for this account.",
            "Whitelist this server's outbound public IP in DhanHQ before retrying.",
            "Regenerate and save a fresh Dhan access token after entitlement or IP whitelist changes.",
        ]
    elif "client id" in lower and "does not match" in lower:
        code = "dhan_client_id_mismatch"
        likely_causes = ["The saved client ID belongs to a different Dhan account than the access token."]
        suggested_actions = ["Update QUANTGRID_BROKER_CLIENT_ID to the dhanClientId shown by Dhan profile.", "Save a fresh token for the same account."]
    elif "token" in lower or "401" in lower or "403" in lower:
        code = "dhan_auth_or_entitlement_rejected"
        likely_causes = [
            "The access token is expired or invalid.",
            "The account lacks Dhan Data API / Option Chain entitlement.",
            "The server IP is not whitelisted with Dhan.",
        ]
        suggested_actions = [
            "Save a fresh Dhan access token.",
            "Confirm Dhan Data APIs / Option Chain entitlement.",
            "Confirm Dhan IP whitelist contains this server's outbound IP.",
        ]
    else:
        suggested_actions = [
            "Retry after checking Dhan Data API status.",
            "Confirm client ID, access token, Data API entitlement, and IP whitelist.",
        ]

    return {
        "provider": provider,
        "status": "BLOCKED",
        "code": code,
        "message": text,
        "profile_login_can_pass": provider == "dhan",
        "live_rows_available": False,
        "likely_causes": likely_causes,
        "suggested_actions": suggested_actions,
        "retry_after_seconds": retry_after_seconds,
    }


def _ensure_dhan_success(payload: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("status") or "").lower() == "failure":
        raise RuntimeError(
            _dhan_failure_message(payload)
            or f"Dhan option-chain API rejected the request. Full response: {json.dumps(payload)[:400]}"
        )
    return payload


def _dhan_sdk_option_payload(path: str, body: dict[str, Any]) -> dict[str, Any]:
    security_id = int(body["UnderlyingScrip"])
    exchange_segment = str(body["UnderlyingSeg"])
    dhan = dhan_sdk_client()
    if path == "optionchain/expirylist":
        method = getattr(dhan, "expiry_list", None)
        if not callable(method):
            raise DhanSdkUnavailable("dhanhq package does not expose expiry_list")
        return _ensure_dhan_success(method(security_id, exchange_segment))
    if path == "optionchain":
        method = getattr(dhan, "option_chain", None)
        if not callable(method):
            raise DhanSdkUnavailable("dhanhq package does not expose option_chain")
        return _ensure_dhan_success(method(security_id, exchange_segment, str(body["Expiry"])))
    raise DhanSdkUnavailable(f"dhanhq package does not expose {path}")


def _dhan_option_provider_payload(path: str, body: dict[str, Any]) -> dict[str, Any]:
    if _dhan_sdk_enabled():
        try:
            return _dhan_sdk_option_payload(path, body)
        except DhanSdkUnavailable:
            pass
    return _dhan_option_payload(path, body)


def _dhan_sdk_enabled() -> bool:
    if os.getenv("DHAN_USE_SDK", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return getattr(dhan_sdk_client, "__module__", "") != "Backend.infrastructure.market_data.dhan_sdk"


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _dhan_response_data(payload: dict[str, Any] | list[Any]) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _dhan_underlying(symbol: str) -> tuple[int, str]:
    normalized = symbol.upper()
    default_security_id, default_segment = DHAN_UNDERLYING_DEFAULTS.get(normalized, (0, ""))
    security_id = (
        os.getenv(f"DHAN_SECURITY_ID_{normalized}")
        or os.getenv(f"QUANTGRID_DHAN_SECURITY_ID_{normalized}")
        or (str(default_security_id) if default_security_id else None)
    )
    exchange_segment = (
        os.getenv(f"DHAN_EXCHANGE_SEGMENT_{normalized}")
        or os.getenv(f"QUANTGRID_DHAN_EXCHANGE_SEGMENT_{normalized}")
        or os.getenv("DHAN_MARKET_EXCHANGE_SEGMENT")
        or default_segment
    )
    if not security_id or not exchange_segment:
        raise RuntimeError(f"Dhan option-chain underlying is not configured for {normalized}.")
    return int(security_id), exchange_segment


def _dhan_expiry_values(payload: dict[str, Any] | list[Any]) -> list[Any]:
    data = _dhan_response_data(payload)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        nested = data.get("data")
        if isinstance(nested, list):
            return nested
        for key in ("expiry", "expiryList", "expiry_list", "expiryDates"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _dhan_option_chain(payload: dict[str, Any]) -> dict[str, Any]:
    data = _dhan_response_data(payload)
    if not isinstance(data, dict):
        return {}
    nested = data.get("data")
    if isinstance(nested, dict) and isinstance(nested.get("oc"), dict):
        return nested["oc"]
    option_chain = data.get("oc") or data.get("optionChain") or data.get("option_chain")
    return option_chain if isinstance(option_chain, dict) else {}


def _dhan_strike_payload(option_chain: dict[str, Any], strike: int) -> dict[str, Any]:
    candidates = {
        str(strike),
        str(float(strike)),
        f"{float(strike):.1f}",
        f"{float(strike):.2f}",
        f"{float(strike):.6f}",
    }
    for key in candidates:
        value = option_chain.get(key)
        if isinstance(value, dict):
            return value
    for key, value in option_chain.items():
        try:
            if int(round(float(key))) == strike and isinstance(value, dict):
                return value
        except (TypeError, ValueError):
            continue
    return {}


def _dhan_leg_payload(payload: dict[str, Any]) -> dict[str, Any]:
    greeks = payload.get("greeks") if isinstance(payload.get("greeks"), dict) else None
    if greeks is None:
        greeks = {
            key: payload[key]
            for key in ("delta", "gamma", "theta", "vega", "rho")
            if key in payload and payload[key] is not None
        } or None
    bid = {
        "price": _first_present(payload, "top_bid_price", "topBidPrice", "bid_price", "bidPrice"),
        "quantity": _first_present(payload, "top_bid_quantity", "topBidQuantity", "bid_quantity", "bidQuantity"),
    }
    ask = {
        "price": _first_present(payload, "top_ask_price", "topAskPrice", "ask_price", "askPrice"),
        "quantity": _first_present(payload, "top_ask_quantity", "topAskQuantity", "ask_quantity", "askQuantity"),
    }
    return {
        "security_id": _first_present(payload, "security_id", "securityId"),
        "ltp": _first_present(payload, "last_price", "lastPrice", "ltp"),
        "change": _first_present(payload, "change", "net_change", "netChange"),
        "volume": _first_present(payload, "volume", "totalTradedVolume"),
        "oi": _first_present(payload, "oi", "open_interest", "openInterest"),
        "iv": _first_present(payload, "implied_volatility", "impliedVolatility", "iv"),
        "oi_change": _first_present(payload, "oi_change", "change_oi", "changeinOpenInterest", "oiChange"),
        "previous_oi": _first_present(payload, "previous_oi", "previousOpenInterest"),
        "greeks": greeks,
        "bid": bid if bid["price"] is not None or bid["quantity"] is not None else None,
        "ask": ask if ask["price"] is not None or ask["quantity"] is not None else None,
    }


def _dhan_option_rows(symbol: str, strikes: list[int]) -> tuple[list[dict[str, Any]], str | None]:
    global _DHAN_OPTION_COOLDOWN_UNTIL

    credentials = dhan_credentials()
    identity = "\0".join((credentials["client_id"] or "", credentials["access_token"] or ""))
    credential_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    cache_key = (symbol.upper(), tuple(strikes), credential_key)

    with _DHAN_OPTION_LOCK:
        now = monotonic()
        shared_remaining = redis_service.cooldown_remaining(_DHAN_OPTION_COOLDOWN_NAME)
        if shared_remaining:
            _DHAN_OPTION_COOLDOWN_UNTIL = max(_DHAN_OPTION_COOLDOWN_UNTIL, now + shared_remaining)
        if now < _DHAN_OPTION_COOLDOWN_UNTIL:
            remaining = max(1, math.ceil(_DHAN_OPTION_COOLDOWN_UNTIL - now))
            raise RuntimeError(f"Dhan option-chain cooldown is active. Retry after {remaining} seconds.")
        cached = _DHAN_OPTION_CACHE.get(cache_key)
        if cached and now < cached[0]:
            return deepcopy(cached[1]), cached[2]

        lock_token = redis_service.acquire_lock(_DHAN_OPTION_FETCH_LOCK_NAME, ttl_seconds=20)
        if lock_token == "":  # nosec B105
            raise RuntimeError("Dhan option-chain refresh is already in progress. Retry after 5 seconds.")
        try:
            security_id, exchange_segment = _dhan_underlying(symbol)
            base_body = {"UnderlyingScrip": security_id, "UnderlyingSeg": exchange_segment}
            expiry_payload = _dhan_option_provider_payload("optionchain/expirylist", base_body)
            expiry_values = _dhan_expiry_values(expiry_payload)
            expiry = next((str(item) for item in expiry_values if item), None)
            if not expiry:
                raise RuntimeError("Dhan did not return an option-chain expiry.")

            chain_payload = _dhan_option_provider_payload("optionchain", base_body | {"Expiry": expiry})
            logger.warning(
                    "DHAN RAW OPTION SAMPLE: %s",
                    json.dumps(chain_payload, default=str)[:2000]
                )
            option_chain = _dhan_option_chain(chain_payload)
        except Exception as exc:
            detail = str(exc).lower()
            if "429" in detail or "too many requests" in detail:
                cooldown = max(60, int(os.getenv("QUANTGRID_DHAN_429_COOLDOWN_SECONDS", "300")))
                _DHAN_OPTION_COOLDOWN_UNTIL = monotonic() + cooldown
                redis_service.start_cooldown(_DHAN_OPTION_COOLDOWN_NAME, ttl_seconds=cooldown)
                raise RuntimeError(f"Dhan rate limit reached; cooldown activated. Retry after {cooldown} seconds.") from exc
            raise
        finally:
            if lock_token:
                redis_service.release_lock(_DHAN_OPTION_FETCH_LOCK_NAME, lock_token)

        rows = []
        for strike in strikes:
            strike_payload = _dhan_strike_payload(option_chain, strike)
            call = strike_payload.get("ce") or strike_payload.get("CE") or {}
            put = strike_payload.get("pe") or strike_payload.get("PE") or {}
            rows.append({
                "strike": strike,
                "ce": _dhan_leg_payload(call) if isinstance(call, dict) else {},
                "pe": _dhan_leg_payload(put) if isinstance(put, dict) else {},
            })
        ttl = max(15, int(os.getenv("QUANTGRID_OPTION_CHAIN_CACHE_SECONDS", "60")))
        _DHAN_OPTION_CACHE[cache_key] = (monotonic() + ttl, deepcopy(rows), expiry)
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
    return {
        "symbol": symbol.upper(),
        "underlying_price": None,
        "spot": None,
        "atm_strike": None,
        "ATM": None,
        "atm": None,
        "step": step,
        "expiry": None,
        "source": "option-chain-unavailable",
        "warning": warning,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rows": [],
        "live_rows_available": False,
        "provider_available": False,
        "fallback_message": warning,
        "data_quality": {
            "status": "unavailable",
            "reason": "live_provider_unavailable",
            "message": warning,
        },
        "pcr": None,
        "PCR": None,
        "max_pain": None,
        "support": None,
        "resistance": None,
        "signals": {
            "bias": "NEUTRAL",
            "reason": warning,
            "total_call_oi": 0,
            "total_put_oi": 0,
            "pcr": None,
            "atm_strike": None,
            "max_pain": None,
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
        raise _market_data_unavailable(exc) from exc


@router.get("/option-chain/{symbol}")
def get_option_chain(
    symbol: str,
    strikes_each_side: int = 5,
    step: int = 50,
    _role: str | None = None,
    _access=Depends(require_entitlement("options.basic")),
):
    strikes_each_side = max(1, min(int(strikes_each_side), 10))
    step = max(1, int(step))
    try:
        access_role = _access.user.role if hasattr(_access, "user") and _access.user is not None else _role
        price_payload = get_price(symbol, _role=access_role)
        price = float(price_payload.get("price") or 0.0)
    except Exception as exc:
        logger.exception("option_chain_price_fetch_failed", extra={"symbol": symbol, "error_type": exc.__class__.__name__})
        observe_option_chain_failure("market-price", exc.__class__.__name__)
        if get_settings().live_trading_enabled:
            return _fallback_option_chain(
                symbol,
                strikes_each_side=strikes_each_side,
                step=step,
                warning=f"Live market price unavailable: {exc}. Option-chain data is unavailable.",
            )
        return _fallback_option_chain(
            symbol,
            strikes_each_side=strikes_each_side,
            step=step,
            warning=f"Live market price unavailable: {exc}. Option-chain data is unavailable.",
        )
    if price <= 0:
        if get_settings().live_trading_enabled:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Current market price is unavailable.")
        return _fallback_option_chain(
            symbol,
            strikes_each_side=strikes_each_side,
            step=step,
            warning="Current market price is unavailable. Option-chain data is unavailable.",
        )

    atm = _nearest_strike(price, step)
    strikes = [atm + (offset * step) for offset in range(-strikes_each_side, strikes_each_side + 1)]
    source = "derived-from-underlying"
    expiry = None
    warning = "Live option-chain provider unavailable. Option-chain rows are hidden until provider data is available."
    provider_available = False
    provider_diagnostics = None

    try:
        rows, expiry = _dhan_option_rows(symbol, strikes)
        if any(row["ce"].get("ltp") is not None or row["pe"].get("ltp") is not None for row in rows):
            source = "dhan-option-chain"
            warning = None
            provider_available = True
            provider_diagnostics = {
                "provider": "dhan",
                "status": "OK",
                "code": "live_option_chain_available",
                "message": "Dhan option-chain rows are available.",
                "live_rows_available": True,
                "likely_causes": [],
                "suggested_actions": [],
            }
        else:
            rows = _derived_option_rows(strikes)
            warning = "Dhan option-chain returned no matching strikes. Option-chain rows are hidden until provider data is available."
            provider_diagnostics = _option_chain_diagnostics(warning)
    except Exception as dhan_exc:
        logger.exception("option_chain_provider_fetch_failed", extra={"symbol": symbol, "provider": "dhan", "error_type": dhan_exc.__class__.__name__})
        observe_option_chain_failure("dhan", dhan_exc.__class__.__name__)
        provider_diagnostics = _option_chain_diagnostics(str(dhan_exc))
        try:
            rows, expiry = _yahoo_option_rows(symbol, strikes)
        except Exception as yahoo_exc:
            logger.exception("option_chain_provider_fetch_failed", extra={"symbol": symbol, "provider": "yahoo", "error_type": yahoo_exc.__class__.__name__})
            observe_option_chain_failure("yahoo", yahoo_exc.__class__.__name__)
            rows = _derived_option_rows(strikes)
            warning = f"Live option-chain provider unavailable: {dhan_exc}. Option-chain rows are hidden until provider data is available."
        else:
            if any(row["ce"].get("ltp") is not None or row["pe"].get("ltp") is not None for row in rows):
                source = "yahoo-finance-options"
                warning = f"Dhan option-chain unavailable: {dhan_exc}. Showing Yahoo option-chain data."
                provider_available = True
            else:
                rows = _derived_option_rows(strikes)
                warning = f"Live option-chain provider unavailable: {dhan_exc}. Option-chain rows are hidden until provider data is available."

    if not provider_available:
        source = "option-chain-unavailable"
        rows = []

    rows, data_quality = validate_option_chain_rows(rows, source=source, expiry=expiry)
    data_quality_payload = data_quality.model_dump()
    fallback_message = warning if not provider_available else None
    if not provider_available:
        data_quality_payload = {
            **data_quality_payload,
            "status": "option_chain_rows_unavailable",
            "reason": "option_chain_rows_unavailable",
            "message": fallback_message,
        }
    call_oi = sum(float(row["ce"].get("oi") or 0) for row in rows)
    put_oi = sum(float(row["pe"].get("oi") or 0) for row in rows)
    pcr = round(put_oi / call_oi, 3) if call_oi else None
    support_rows = [row for row in rows if row["strike"] < atm]
    resistance_rows = [row for row in rows if row["strike"] > atm]
    support = max(support_rows, key=lambda row: float(row["pe"].get("oi") or 0))["strike"] if support_rows else None
    resistance = max(resistance_rows, key=lambda row: float(row["ce"].get("oi") or 0))["strike"] if resistance_rows else None
    result = {
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
        "provider_diagnostics": provider_diagnostics,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "live_rows_available": provider_available and bool(rows),
        "fallback_message": fallback_message,
        "data_quality": data_quality_payload,
        "pcr": pcr,
        "PCR": pcr,
        "max_pain": atm if provider_available else None,
        "support": support,
        "resistance": resistance,
        "provider_available": provider_available,
    }
    _LATEST_OPTION_CONTEXT[symbol.upper()] = _option_context_from_payload(result)
    return result


def _option_context_from_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = list(payload.get("rows") or [])
    source = str(payload.get("source") or "unknown")
    timestamp = str(payload.get("updated_at") or datetime.now(timezone.utc).isoformat())
    quality = payload.get("data_quality") or {}
    provider_available = bool(payload.get("provider_available") and rows)
    settings = get_settings()
    live_suitable = bool(
        provider_available
        and quality.get("status") == "PASS"
        and (source == "dhan-option-chain" or (source == "yahoo-finance-options" and settings.allow_yahoo_for_live))
    )
    call_oi = sum(float(row.get("ce", {}).get("oi") or 0) for row in rows)
    put_oi = sum(float(row.get("pe", {}).get("oi") or 0) for row in rows)
    pcr = payload.get("pcr")
    pcr_number = float(pcr) if pcr is not None else None
    oi_bias = "BULLISH" if pcr_number is not None and pcr_number >= 1.15 else "BEARISH" if pcr_number is not None and pcr_number <= 0.85 else "NEUTRAL"
    iv_values = [
        float(leg.get("iv"))
        for row in rows
        for leg in (row.get("ce", {}), row.get("pe", {}))
        if leg.get("iv") is not None
    ]
    average_iv = round(sum(iv_values) / len(iv_values), 3) if iv_values else None

    def observation(value: Any, *, available: bool = True) -> dict[str, Any]:
        return {
            "value": value,
            "source": source,
            "timestamp": timestamp,
            "available": bool(provider_available and available and value is not None),
            "live_suitable": live_suitable,
        }

    return {
        "oi_bias": observation(oi_bias, available=pcr_number is not None),
        "pcr": observation(pcr_number),
        "call_oi": observation(call_oi, available=call_oi > 0),
        "put_oi": observation(put_oi, available=put_oi > 0),
        "iv": observation(average_iv),
    }


_OPTION_CANDLE_INTERVALS = {"1m": 1, "5m": 5, "15m": 15, "25m": 25, "60m": 60}


@router.get("/signals")
def get_signals():
    return {"signals": []}


@router.get("/volume-analysis")
def get_volume_analysis(
    symbol: str = "NIFTY",
    timeframe: str = "1m",
    period: str = "1d",
    limit: int = 100,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    candles_payload = market_service.get_candles(symbol, interval=timeframe, period=period, limit=limit, _role=_role)
    result = analyze_volume(
        symbol=symbol,
        timeframe=timeframe,
        candles=list(candles_payload.get("candles") or []),
    ).to_dict()
    return {
        **result,
        "source": candles_payload.get("source"),
        "volume_status": candles_payload.get("volume_status"),
        "data_quality": candles_payload.get("data_quality"),
    }


@router.post("/volume-analysis")
def post_volume_analysis(
    payload: dict[str, Any] = Body(...),
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst")),
):
    candles = payload.get("candles")
    if not isinstance(candles, list):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="candles must be a list of OHLCV rows.")
    result = analyze_volume(
        symbol=str(payload.get("symbol") or "NIFTY"),
        timeframe=str(payload.get("timeframe") or payload.get("interval") or "1m"),
        candles=candles,
        delivery_data=payload.get("delivery_data") if isinstance(payload.get("delivery_data"), list) else None,
    )
    return result.to_dict()


@router.get("/option-candles/{security_id}")
def get_option_candles(
    security_id: str,
    interval: str = "1m",
    limit: int = 120,
    symbol: str = "NIFTY",
    strike: float | None = None,
    side: str | None = None,
    _access=Depends(require_entitlement("options.basic")),
):
    """Return provider-backed candles for one active NSE index-option contract."""
    normalized_security_id = str(security_id or "").strip()
    if normalized_security_id.lower() == "resolve":
        normalized_side = str(side or "").strip().lower()
        if strike is None or normalized_side not in {"ce", "pe"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Strike and option side are required to resolve the Dhan contract.",
            )
        try:
            resolved_rows, _expiry = _dhan_option_rows(symbol, [int(round(strike))])
            resolved_leg = resolved_rows[0].get(normalized_side, {}) if resolved_rows else {}
            normalized_security_id = str(resolved_leg.get("security_id") or "").strip()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Dhan could not resolve this option contract: {exc}",
            ) from exc
        if not normalized_security_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dhan returned the option quote without a contract security ID. Update the backend and Dhan SDK, then refresh the chain.",
            )
    if not normalized_security_id.isdigit():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A valid Dhan option security ID is required.")
    if interval not in _OPTION_CANDLE_INTERVALS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Supported intervals are 1m, 5m, 15m, 25m, and 60m.")

    limit = max(1, min(int(limit), 500))
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    # Include prior sessions so the drawer still works after hours, on holidays,
    # and before the first candle of the current trading day.
    from_time = (now - timedelta(days=5)).replace(hour=9, minute=15, second=0, microsecond=0)
    try:
        raw = dhan_sdk_client().intraday_minute_data(
            security_id=normalized_security_id,
            exchange_segment="NSE_FNO",
            instrument_type="OPTIDX",
            interval=_OPTION_CANDLE_INTERVALS[interval],
            oi=True,
            from_date=from_time.strftime("%Y-%m-%d %H:%M:%S"),
            to_date=now.strftime("%Y-%m-%d %H:%M:%S"),
        )
        if isinstance(raw, dict) and str(raw.get("status", "")).lower() == "failed":
            raise RuntimeError(str(raw.get("remarks") or raw.get("data") or "Dhan rejected the option candle request."))
        candles = _normalize_candles(f"OPTION-{normalized_security_id}", raw)[-limit:]
        if not candles:
            raise RuntimeError("Dhan returned no candles for this option contract.")
        return {
            "security_id": normalized_security_id,
            "exchange_segment": "NSE_FNO",
            "instrument": "OPTIDX",
            "interval": interval,
            "source": "dhan-option-candles",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "candles": candles,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("dhan_option_candles_failed", extra={"security_id": normalized_security_id, "interval": interval, "error_type": exc.__class__.__name__})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Live option candles unavailable from Dhan: {exc}",
        ) from exc


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
        candles, data_quality = validate_candles(candles, source=str(source))

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
            "data_quality": data_quality.model_dump(),
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
        # NOTE: this used to discard `exc` entirely -- no logging, no detail in the response
        # -- so every failed live-candle fetch silently fell back to whatever was last
        # successfully stored, with zero visibility into why it kept failing. That's
        # precisely how candles can get stuck hours stale during open market hours without
        # anyone noticing until they see the age warning on the dashboard: the failure
        # producing that staleness was invisible. Log it server-side and include the real
        # reason in the response so provider outages cannot silently resemble fresh data.
        logger.warning(
            "live_candle_fetch_failed_serving_cache",
            extra={"symbol": symbol, "interval": interval, "error_type": exc.__class__.__name__, "error": str(exc)},
        )
        cached = _stored_candle_response(symbol, interval, period, limit)
        if cached:
            cached["warning"] = f"Live market data provider is unavailable ({exc.__class__.__name__}: {exc}); served latest stored live candles."
            return cached
        raise _market_data_unavailable(exc) from exc


@router.get("/validation/{symbol}")
def get_candle_validation(
    symbol: str,
    interval: str = "1m",
    period: str = "1d",
    limit: int = 100,
    mode: str = "paper",
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
):
    response = market_service.get_candles(symbol, interval=interval, period=period, limit=limit)
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
