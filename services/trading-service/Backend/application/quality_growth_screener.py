"""Read-only V2 quality-growth screener backed by a dated, authorized feed.

The feed must be supplied by an approved data license or by a local, regularly
updated export. This module neither scrapes Screener.in nor submits orders.
The API re-fetches at a bounded interval when queried; it never invents data.
"""
from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from Backend.infrastructure.http_safety import require_https_url

_MAX_BYTES = 2_000_000
_MAX_STOCKS = 1500
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_REQUIRED = (
    "market_cap_cr", "roe", "roce", "debt_to_equity",
    "sales_growth_3y", "profit_growth_3y", "opm", "pledged_percentage",
    "cash_from_operations_cr", "pe", "current_price", "dma200",
    "avg_daily_volume_1m",
)
_WEIGHTS = {"quality": 30, "growth": 25, "valuation": 20, "momentum": 15, "risk": 10}
_DISCLAIMER = "Research watchlist only; not a trade recommendation or order signal."


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Feed redirects are not permitted")


def _positive_seconds() -> int:
    try:
        return min(3600, max(60, int(os.getenv("QUANTGRID_QUALITY_GROWTH_REFRESH_SECONDS", "900"))))
    except ValueError:
        return 900


def _source() -> tuple[str, str]:
    """One configured source only, with an explicit allowlist for HTTPS requests."""
    local = os.getenv("QUANTGRID_QUALITY_GROWTH_FEED_PATH", "").strip()
    remote = os.getenv("QUANTGRID_QUALITY_GROWTH_FEED_URL", "").strip()
    if bool(local) == bool(remote):
        return ("unconfigured", "")
    if local:
        path = Path(local)
        if not path.is_absolute():
            raise ValueError("Feed file path must be absolute")
        # The operator controls this root-owned file; avoid server source/secret files.
        if path.suffix.lower() != ".json":
            raise ValueError("Feed file must be JSON")
        return ("file", str(path))
    host = os.getenv("QUANTGRID_QUALITY_GROWTH_ALLOWED_HOST", "").strip().lower()
    if not host or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{2,252}", host):
        raise ValueError("An explicit HTTPS data-provider host is required")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("Local network hosts are not accepted")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("Feed host must be a DNS name, not an IP address")
    require_https_url(remote, allowed_hosts={host})
    parts = urlsplit(remote)
    if parts.port not in (None, 443):
        raise ValueError("Only standard HTTPS port 443 is permitted")
    return ("https", remote)


def _read_source(kind: str, location: str) -> dict[str, Any]:
    if kind == "file":
        with open(location, "rb") as file:
            raw = file.read(_MAX_BYTES + 1)
    elif kind == "https":
        headers = {"Accept": "application/json", "User-Agent": "QuantGrid-Research/2.0"}
        # Credentials never enter logs, exception strings or API results.
        token = os.getenv("QUANTGRID_QUALITY_GROWTH_FEED_TOKEN", "").strip()
        if token:
            headers["Authorization"] = "Bearer " + token
        request = Request(location, headers=headers)
        with build_opener(_NoRedirect).open(request, timeout=8) as response:
            raw = response.read(_MAX_BYTES + 1)
    else:
        raise ValueError("No data feed configured")
    if len(raw) > _MAX_BYTES:
        raise ValueError("Feed is larger than the configured safety limit")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Feed must be a JSON object")
    return data


def _date(raw: Any) -> date:
    if not isinstance(raw, str):
        raise ValueError("Missing observation date")
    return date.fromisoformat(raw)


def _age_days(day: date, now: date) -> int:
    return (now - day).days


def _number(item: dict[str, Any], field: str) -> float | None:
    value = item.get(field)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _cap(value: float) -> float:
    return max(0.0, min(100.0, value))


def _bucket(market_cap: float, segment: str) -> str:
    if segment == "SME":
        return "SME"
    if market_cap < 2000:
        return "EMERGING"
    if market_cap < 10000:
        return "SMALLER"
    if market_cap < 50000:
        return "MID_SIZED"
    return "LARGER"


def _score(values: dict[str, float]) -> dict[str, float]:
    quality = (_cap(values["roe"] / 25 * 100) + _cap(values["roce"] / 30 * 100) + 100) / 3
    growth = (_cap(values["sales_growth_3y"] / 25 * 100) + _cap(values["profit_growth_3y"] / 25 * 100)) / 2
    valuation = _cap(100 * 20 / values["pe"])
    # If DMA50 is missing, momentum does not get an assumed positive crossover.
    momentum = 60.0 if values.get("dma50") is None else (
        100.0 if values["dma50"] > values["dma200"] and values["current_price"] > values["dma50"]
        else 40.0
    )
    risk = (_cap((0.5 - values["debt_to_equity"]) / 0.5 * 100) +
            _cap((5 - values["pledged_percentage"]) / 5 * 100)) / 2
    raw = {
        "quality": quality, "growth": growth, "valuation": valuation,
        "momentum": momentum, "risk": risk,
    }
    return {key: round(raw[key] * _WEIGHTS[key] / 100, 2) for key in _WEIGHTS}


def evaluate_stock(item: dict[str, Any], *, today: date) -> dict[str, Any]:
    """Never award a score or rank to an incomplete, stale, or failed candidate."""
    symbol = str(item.get("symbol") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9&._-]{0,24}", symbol):
        raise ValueError("Invalid stock symbol")
    name = str(item.get("name") or symbol)[:120]
    segment = str(item.get("market_segment") or "UNKNOWN").strip().upper()
    sector = str(item.get("sector") or "Unknown")[:80]
    values = {field: _number(item, field) for field in (*_REQUIRED, "dma50")}
    missing = [field for field in _REQUIRED if values[field] is None]
    result: dict[str, Any] = {
        "symbol": symbol, "name": name, "sector": sector, "market_segment": segment,
        "status": "UNVERIFIED", "reasons": [], "score": None, "component_scores": {},
        "market_cap_bucket": None, "fundamentals_as_of": item.get("fundamentals_as_of"),
        "price_as_of": item.get("price_as_of"), "source": "verified-feed",
    }
    if missing:
        result["reasons"] = ["Missing or invalid fields: " + ", ".join(missing)]
        return result
    v = {k: float(value) for k, value in values.items() if value is not None}
    result["market_cap_bucket"] = _bucket(v["market_cap_cr"], segment)
    try:
        fundamentals_age = _age_days(_date(item.get("fundamentals_as_of")), today)
        price_age = _age_days(_date(item.get("price_as_of")), today)
    except ValueError:
        result["reasons"] = ["Source timestamps are missing or invalid"]
        return result
    if not (0 <= fundamentals_age <= 180 and 0 <= price_age <= 7):
        result["reasons"] = ["Source fundamentals or price is stale or future-dated"]
        return result
    if segment not in {"MAINBOARD", "SME"}:
        result["reasons"] = ["Exchange segment unverified"]
        return result
    if sector.casefold() in {"financials", "bank", "banking", "nbfc", "insurance"}:
        result["reasons"] = ["Financial businesses require sector-specific ratios"]
        return result
    if (v["pe"] <= 0 or v["current_price"] <= 0 or v["dma200"] <= 0 or
            v["avg_daily_volume_1m"] < 0 or v["debt_to_equity"] < 0 or
            not 0 <= v["pledged_percentage"] <= 100):
        result["reasons"] = ["One or more monetary/ratio fields are out of range"]
        return result

    conditions = (
        ("Market cap must exceed Rs 300 crore", v["market_cap_cr"] > 300),
        ("ROE must exceed 15%", v["roe"] > 15),
        ("ROCE must exceed 18%", v["roce"] > 18),
        ("Debt/equity must be below 0.5", v["debt_to_equity"] < 0.5),
        ("Three-year sales growth must exceed 12%", v["sales_growth_3y"] > 12),
        ("Three-year profit growth must exceed 12%", v["profit_growth_3y"] > 12),
        ("Operating margin must exceed 12%", v["opm"] > 12),
        ("Pledged shares must be below 5%", v["pledged_percentage"] < 5),
        ("Operating cash flow must be positive", v["cash_from_operations_cr"] > 0),
        ("P/E must be below 60", v["pe"] < 60),
        ("Price must exceed 200-day average", v["current_price"] > v["dma200"]),
        ("Average traded value must exceed Rs 30 lakh/day",
         v["current_price"] * v["avg_daily_volume_1m"] > 3_000_000),
    )
    failed = [reason for reason, passes in conditions if not passes]
    if failed:
        result.update(status="REJECTED", reasons=failed)
        return result
    components = _score(v)
    score = round(sum(components.values()), 2)
    reasons: list[str] = []
    if values["dma50"] is None:
        reasons.append("50-day average missing; momentum is not fully verified")
    if segment == "SME":
        reasons.append("SME: manual lot-size, spread, trade-frequency and circuit checks required")
    result.update(
        status="QUALIFIED", score=score, component_scores=components,
        reasons=reasons, research_priority=(
            "HIGH" if score >= 80 and segment == "MAINBOARD"
            else "RESEARCH" if score >= 65 and segment == "MAINBOARD"
            else "MANUAL_REVIEW"
        ),
    )
    return result


def build_screen_snapshot(payload: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    today = current.astimezone(timezone.utc).date()
    source = str(payload.get("source") or "").strip()
    if not source or len(source) > 100:
        raise ValueError("Feed must identify its data provider")
    dated = _date(payload.get("as_of"))
    if not 0 <= _age_days(dated, today) <= 7:
        raise ValueError("Feed snapshot is stale or future-dated")
    rows = payload.get("stocks")
    if not isinstance(rows, list) or len(rows) > _MAX_STOCKS:
        raise ValueError("Expected an array of at most 1500 stocks")
    reviewed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("Invalid row in licensed feed")
        result = evaluate_stock(item, today=today)
        if result["symbol"] in seen:
            raise ValueError("Duplicate symbols in feed")
        seen.add(result["symbol"])
        reviewed.append(result)
    qualified = sorted(
        (item for item in reviewed if item["status"] == "QUALIFIED"),
        key=lambda item: (-item["score"], item["symbol"]),
    )
    return {
        "status": "READY", "source": source, "as_of": dated.isoformat(),
        "refreshed_at": current.isoformat(), "total": len(reviewed),
        "qualified_count": len(qualified), "items": qualified,
        "excluded": [item for item in reviewed if item["status"] != "QUALIFIED"],
        "weights": _WEIGHTS, "disclaimer": _DISCLAIMER,
        "auto_refresh_seconds": _positive_seconds(),
        "execution_enabled": False,
    }


def latest_quality_growth_screen(*, force: bool = False) -> dict[str, Any]:
    """Timed, request-driven feed refresh. Fail closed if source/parse is invalid."""
    try:
        kind, location = _source()
        if kind == "unconfigured":
            raise ValueError("Licensed screening feed not configured")
        key = kind + ":" + location
        now = time.monotonic()
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
            if not force and cached and now < cached[0]:
                return cached[1]
            try:
                value = build_screen_snapshot(_read_source(kind, location))
            except Exception:
                value = {
                    "status": "UNAVAILABLE", "items": [], "excluded": [],
                    "qualified_count": 0, "source": "unavailable",
                    "reason": "Data provider unavailable, invalid, or stale; no stocks ranked.",
                    "execution_enabled": False, "disclaimer": _DISCLAIMER,
                }
            _CACHE[key] = (now + _positive_seconds(), value)
            return value
    except (ValueError, OSError):
        return {
            "status": "UNCONFIGURED", "items": [], "excluded": [],
            "qualified_count": 0, "source": "unavailable",
            "reason": "Configure a licensed JSON feed path or an allowlisted HTTPS feed.",
            "execution_enabled": False, "disclaimer": _DISCLAIMER,
        }
