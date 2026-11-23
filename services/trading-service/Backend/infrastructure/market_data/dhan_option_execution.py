"""Read-only Dhan instrument master and per-contract executable depth for paper fills."""
from __future__ import annotations

import csv
import io
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

from Backend.application.options.contract_master_verification import verify_nifty_option_contract
from Backend.application.options.quote_freshness import verify_exchange_quote_timestamp
from Backend.infrastructure.http_safety import require_https_url

IST = timezone(timedelta(hours=5, minutes=30))
MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
_master_lock = threading.Lock()
_master_date = None
_master_rows: list[dict] = []
_quote_lock = threading.Lock()
_last_quote_request = 0.0


def _positive(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_option_{name}") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"invalid_option_{name}")
    return number


def parse_master(text: str) -> list[dict]:
    rows = []
    for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        if (row.get("EXCH_ID") != "NSE" or row.get("SEGMENT") != "D"
                or row.get("INSTRUMENT") != "OPTIDX"
                or row.get("UNDERLYING_SYMBOL") != "NIFTY"):
            continue
        expiry = str(row.get("SM_EXPIRY_DATE", ""))[:10]
        if expiry < datetime.now(IST).date().isoformat():
            continue
        lot = _positive(row.get("LOT_SIZE"), "lot_size")
        if not lot.is_integer():
            raise ValueError("invalid_option_lot_size")
        contract = verify_nifty_option_contract(
            master_row={
                "security_id": row.get("SECURITY_ID"), "underlying": "NIFTY",
                "segment": "NSE_FNO", "side": row.get("OPTION_TYPE"),
                "expiry": str(row.get("SM_EXPIRY_DATE", ""))[:10],
                "strike": _positive(row.get("STRIKE_PRICE"), "strike"), "lot_size": int(lot),
            },
            security_id=row.get("SECURITY_ID"), expiry=str(row.get("SM_EXPIRY_DATE", ""))[:10],
            strike=_positive(row.get("STRIKE_PRICE"), "strike"), side=row.get("OPTION_TYPE"),
            lot_size=int(lot),
        )
        rows.append(contract)
    if not rows:
        raise ValueError("nifty_option_master_unavailable")
    return rows


def instrument_master() -> list[dict]:
    global _master_date, _master_rows
    today = datetime.now(IST).date()
    with _master_lock:
        if _master_date != today:
            url = require_https_url(MASTER_URL, allowed_hosts={"images.dhan.co"})
            with urlopen(Request(url, headers={"User-Agent": "QuantGrid/1.0"}), timeout=15) as response:  # nosec B310
                text = response.read(100_000_001)
            if len(text) > 100_000_000:
                raise ValueError("option_master_too_large")
            _master_rows = parse_master(text.decode("utf-8"))
            _master_date = today
        return list(_master_rows)


def select_contract(spot: float, option_type: str, *, rows=None, now=None) -> dict:
    if option_type not in {"CE", "PE"}:
        raise ValueError("invalid_option_type")
    clock = now or datetime.now(IST)
    available = [row for row in (instrument_master() if rows is None else rows)
                 if row["side"] == option_type and row["expiry"] >= clock.astimezone(IST).date().isoformat()]
    if not available:
        raise ValueError("no_active_option_contract")
    expiry = min(row["expiry"] for row in available)
    available = [row for row in available if row["expiry"] == expiry]
    strike = min((row["strike"] for row in available), key=lambda strike: (abs(strike - spot), strike))
    matches = [row for row in available if row["strike"] == strike]
    if len(matches) != 1:
        raise ValueError("ambiguous_option_contract")
    return matches[0]


def parse_quote(security_id: str, payload: dict, *, now=None) -> dict:
    if payload.get("status") != "success":
        raise ValueError("option_quote_unavailable")
    raw = payload.get("data", {}).get("NSE_FNO", {}).get(str(security_id))
    if not isinstance(raw, dict):
        raise ValueError("option_quote_identity_missing")
    # Dhan REST market-depth documents last_trade_time in DD/MM/YYYY HH:MM:SS.
    # NSE trades use IST. This remains the provider trade time, never fetch time.
    try:
        traded_at = datetime.strptime(raw["last_trade_time"], "%d/%m/%Y %H:%M:%S").replace(tzinfo=IST)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("option_trade_timestamp_missing") from exc
    verify_exchange_quote_timestamp(traded_at.isoformat(), now=now)
    buys = [level for level in raw.get("depth", {}).get("buy", [])
            if float(level.get("price") or 0) > 0 and float(level.get("quantity") or 0) > 0]
    sells = [level for level in raw.get("depth", {}).get("sell", [])
             if float(level.get("price") or 0) > 0 and float(level.get("quantity") or 0) > 0]
    if not buys or not sells:
        raise ValueError("option_depth_unavailable")
    buy = max(buys, key=lambda level: float(level["price"]))
    sell = min(sells, key=lambda level: float(level["price"]))
    bid, ask = float(buy["price"]), float(sell["price"])
    bid, ask = _positive(bid, "bid"), _positive(ask, "ask")
    if bid > ask:
        raise ValueError("crossed_option_depth")
    return {"security_id": str(security_id), "bid": bid, "ask": ask,
            "bid_quantity": int(buy["quantity"]), "ask_quantity": int(sell["quantity"]),
            "quote_timestamp": traded_at.isoformat(), "quote_source": "dhan-marketfeed-quote"}


def contract_quotes(security_ids: list[str]) -> dict[str, dict]:
    global _last_quote_request
    from Backend.presentation.api.market_api import _dhan_option_payload

    if not security_ids:
        return {}
    ids = list(dict.fromkeys(str(value) for value in security_ids))
    if any(not value.isdecimal() or int(value) <= 0 for value in ids) or len(ids) > 1000:
        raise ValueError("invalid_option_quote_ids")
    # Respect the documented one request/second REST depth limit per process.
    with _quote_lock:
        delay = 1.0 - (time.monotonic() - _last_quote_request)
        if delay > 0:
            time.sleep(delay)
        _last_quote_request = time.monotonic()
        payload = _dhan_option_payload("marketfeed/quote", {"NSE_FNO": [int(value) for value in ids]})
    return {value: parse_quote(value, payload) for value in ids}
