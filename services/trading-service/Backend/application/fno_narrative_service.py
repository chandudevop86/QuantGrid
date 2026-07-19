from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.narratives.fo_narrative_loop import NarrativeInput, NarrativeSignal, generate_narrative_signal
from Backend.application.market_data_store import latest_candles, latest_price_tick
from Backend.application.quant_modules import live_nse_option_chain, option_chain_engine
from Backend.application.market_data_service import get_market_data_service
from app.validation.data_quality import validate_option_chain_rows


_LATEST: dict[str, NarrativeSignal] = {}


def latest_narrative(symbol: str = "NIFTY") -> NarrativeSignal | None:
    return _LATEST.get(symbol.upper())


def run_fno_narrative(symbol: str = "NIFTY", *, overrides: dict[str, Any] | None = None) -> NarrativeSignal:
    payload = build_narrative_input(symbol, overrides=overrides)
    signal = generate_narrative_signal(payload)
    _LATEST[payload.symbol.upper()] = signal
    return signal


def build_narrative_input(symbol: str = "NIFTY", *, overrides: dict[str, Any] | None = None) -> NarrativeInput:
    symbol = symbol.upper()
    spot_payload = _spot_payload(symbol)
    spot = float(spot_payload.get("price") or spot_payload.get("ltp") or 0.0)
    chain_payload = _option_chain_payload(symbol)
    rows, option_chain_quality = validate_option_chain_rows(
        list(chain_payload.get("rows") or []),
        source=str(chain_payload.get("source") or "unknown"),
    )
    previous_spot = _previous_spot(symbol)
    base = {
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc),
        "spot_price": spot,
        "futures_price": _env_float(f"QUANTGRID_{symbol}_FUTURES_PRICE") or _env_float("QUANTGRID_FUTURES_PRICE") or spot,
        "option_chain": rows,
        "option_chain_quality": option_chain_quality.model_dump(),
        "pcr": chain_payload.get("pcr") or chain_payload.get("PCR"),
        "india_vix": _env_float("INDIA_VIX"),
        "india_vix_change_pct": _env_float("INDIA_VIX_CHANGE_PCT"),
        "fii_cash": _env_float("FII_CASH_FLOW"),
        "dii_cash": _env_float("DII_CASH_FLOW"),
        "fii_index_futures": _env_float("FII_INDEX_FUTURES"),
        "max_pain": chain_payload.get("max_pain"),
        "gift_nifty_change_pct": _env_float("GIFT_NIFTY_CHANGE_PCT"),
        "usdinr_change_pct": _env_float("USDINR_CHANGE_PCT"),
        "brent_change_pct": _env_float("BRENT_CHANGE_PCT"),
        "global_market_cues": _env_float("GLOBAL_MARKET_CUES"),
        "previous_spot": previous_spot,
        "is_expiry_day": _env_bool("QUANTGRID_EXPIRY_DAY"),
        "days_to_expiry": _env_int("QUANTGRID_DAYS_TO_EXPIRY"),
    }
    if overrides:
        base.update(overrides)
    return NarrativeInput.model_validate(base)


def _spot_payload(symbol: str) -> dict[str, Any]:
    try:
        return get_market_data_service().get_ltp(symbol, mode="paper")
    except Exception:
        cached = latest_price_tick(symbol)
        if cached:
            return cached
        return {"symbol": symbol, "price": _env_float(f"QUANTGRID_{symbol}_SPOT") or _env_float("QUANTGRID_SPOT") or 0.0}


def _option_chain_payload(symbol: str) -> dict[str, Any]:
    try:
        return live_nse_option_chain(symbol)
    except Exception:
        return option_chain_engine(symbol)


def _previous_spot(symbol: str) -> float | None:
    candles = latest_candles(symbol, "1m", 2) or latest_candles(symbol, "5m", 2)

    if len(candles) < 2:
        return None

    close = candles[-2].get("close")

    if close is None:
        return None

    try:
        return float(close)
    except (TypeError, ValueError):
        return None
def _env_float(name: str) -> float | None:
    raw = os.getenv(name)
    if raw in {None, ""}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _env_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw in {None, ""}:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _env_bool(name: str) -> bool:
    return str(os.getenv(name) or "").strip().lower() in {"1", "true", "yes"}
