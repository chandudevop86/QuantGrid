"""Read NSE-published institutional EOD reports without inventing missing values.

Opt-in through QUANTGRID_INSTITUTIONAL_AUTO_FETCH=true. This module is
read-only and never affects execution or order routing.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

CASH_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
PARTICIPANT_URL = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{date}.csv"
REPORTS_URL = "https://www.nseindia.com/all-reports-derivatives"
_CASH_PAGE = "https://www.nseindia.com/reports/fii-dii"
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_MAX_BYTES = 1_000_000
_MAX_AGE_DAYS = 5


def auto_fetch_enabled() -> bool:
    return os.getenv("QUANTGRID_INSTITUTIONAL_AUTO_FETCH", "false").strip().lower() in {"1", "true", "yes"}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def _market_date(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(ZoneInfo("Asia/Kolkata")).date()


def _valid_date(raw: str, today: date) -> date | None:
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw.strip(), fmt).date()
            return parsed if 0 <= (today - parsed).days <= _MAX_AGE_DAYS else None
        except ValueError:
            continue
    return None


def parse_cash_activity(payload: Any, *, today: date) -> dict[str, dict[str, Any]]:
    """Normalize the NSE cash API list; require a dated, recent published row."""
    if not isinstance(payload, list):
        raise ValueError("NSE FII/DII response is not a list")
    parsed: dict[str, dict[str, Any]] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        category = str(row.get("category") or "").strip().upper().replace(" ", "")
        key = "fii_cash" if category in {"FII", "FII/FPI", "FPI"} else "dii_cash" if category == "DII" else None
        if key is None:
            continue
        report_date = _valid_date(str(row.get("date") or ""), today)
        value = _number(row.get("netValue"))
        if report_date is None or value is None:
            continue
        candidate = {
            "value": value,
            "unit": "crore",
            "as_of": report_date.isoformat(),
            "source": "nse-eod",
            "source_url": _CASH_PAGE,
        }
        if key not in parsed or candidate["as_of"] > parsed[key]["as_of"]:
            parsed[key] = candidate
    # The two flows must be from the same session; never mix dates.
    if len(parsed) == 2 and parsed["fii_cash"]["as_of"] != parsed["dii_cash"]["as_of"]:
        raise ValueError("FII and DII data have different trading dates")
    return parsed


def parse_participant_oi(text: str, *, report_date: date, today: date) -> dict[str, dict[str, Any]]:
    """Read NSE's participant OI CSV. Index futures OI is NOT NIFTY-only."""
    if not (0 <= (today - report_date).days <= _MAX_AGE_DAYS):
        raise ValueError("participant report is stale or future-dated")
    lines = io.StringIO(text.lstrip("\ufeff")).read().splitlines()
    header_at = next(
        (i for i, line in enumerate(lines) if "Client Type" in line and "Future Index Long" in line),
        None,
    )
    if header_at is None:
        raise ValueError("participant report has no expected column headers")
    reader = csv.DictReader(lines[header_at:], skipinitialspace=True)
    for raw_row in reader:
        row = {str(k).strip(): v for k, v in raw_row.items() if k is not None}
        category = str(row.get("Client Type") or "").strip().upper()
        if category not in {"FII", "FPI", "FII/FPI"}:
            continue
        long = _number(row.get("Future Index Long"))
        short = _number(row.get("Future Index Short"))
        if long is None or short is None or long < 0 or short < 0:
            raise ValueError("participant futures OI missing or invalid")
        total = long + short
        meta = {
            "unit": "contracts",
            "as_of": report_date.isoformat(),
            "source": "nse-participant-oi-eod",
            "source_url": REPORTS_URL,
            "scope": "all_index_futures",
        }
        return {
            "fii_index_futures": {**meta, "value": long - short},
            "fii_index_long": {**meta, "value": long},
            "fii_index_short": {**meta, "value": short},
            "fii_index_long_pct": {**meta, "value": round(long / total * 100, 2) if total else None, "unit": "%"},
        }
    raise ValueError("participant report has no FII row")


def _fetch_text(url: str) -> str:
    if urlsplit(url).scheme != "https" or urlsplit(url).hostname not in {"www.nseindia.com", "nsearchives.nseindia.com"}:
        raise ValueError("untrusted NSE host")
    req = Request(
        url,
        headers={
            "User-Agent": "QuantGrid/1.0 (institutional EOD reporting)",
            "Accept": "application/json, text/csv;q=0.9, */*;q=0.1",
            "Referer": "https://www.nseindia.com/",
        },
    )
    with urlopen(req, timeout=5) as response:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname not in {"www.nseindia.com", "nsearchives.nseindia.com"}:
            raise ValueError("unexpected report redirect")
        content = response.read(_MAX_BYTES + 1)
        if len(content) > _MAX_BYTES:
            raise ValueError("NSE report exceeds size limit")
        return content.decode("utf-8-sig")


def fetch_institutional_eod(*, today: date | None = None) -> dict[str, Any]:
    """Fetch daily reports. Fail closed per source, without stale cached substitutions."""
    today = today or _market_date()
    data: dict[str, Any] = {
        "cash_flows": {},
        "futures": {},
        "warnings": [],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        cash = parse_cash_activity(json.loads(_fetch_text(CASH_URL)), today=today)
        data["cash_flows"].update(cash)
        if len(cash) != 2:
            data["warnings"].append("NSE cash report incomplete or older than five days.")
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        data["warnings"].append(f"NSE FII/DII cash feed unavailable ({type(exc).__name__}).")

    # NSE's participant-wise OI file is issued EOD, not intraday.
    # Check the latest weekdays (including today) to handle nontrading days.
    for offset in range(_MAX_AGE_DAYS + 1):
        session = today - timedelta(days=offset)
        if session.weekday() >= 5:
            continue
        url = PARTICIPANT_URL.format(date=session.strftime("%d%m%Y"))
        try:
            parsed = parse_participant_oi(_fetch_text(url), report_date=session, today=today)
        except (OSError, ValueError, UnicodeError):
            continue
        data["futures"].update(parsed)
        break
    if not data["futures"]:
        data["warnings"].append("NSE participant futures OI unavailable; FII positioning not confirmed.")
    return data


def get_institutional_eod() -> dict[str, Any]:
    """Request-scoped dashboard reader with a bounded TTL, including negative caching."""
    if not auto_fetch_enabled():
        return {"cash_flows": {}, "futures": {}, "warnings": [], "checked_at": None}
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get("institutional")
        if cached and now < cached[0]:
            return {**cached[1], "warnings": list(cached[1]["warnings"])}
        try:
            snapshot = fetch_institutional_eod()
        except Exception:
            # A broken report may never become an invented green trading signal.
            snapshot = {
                "cash_flows": {}, "futures": {},
                "warnings": ["NSE institutional ingestion failed; values unavailable."],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        _CACHE["institutional"] = (now + 900, snapshot)
        return {**snapshot, "warnings": list(snapshot["warnings"])}
