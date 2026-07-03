from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


ENV_METRICS: dict[str, tuple[str, str, str | None]] = {
    "fii_cash": ("FII Cash", "FII_CASH_FLOW", "crore"),
    "dii_cash": ("DII Cash", "DII_CASH_FLOW", "crore"),
    "fii_index_futures": ("FII Index Futures", "FII_INDEX_FUTURES", "contracts"),
    "gift_nifty": ("GIFT NIFTY", "GIFT_NIFTY", None),
    "india_vix": ("India VIX", "INDIA_VIX", None),
    "usd_inr": ("USDINR", "USDINR", None),
    "crude_oil": ("Crude Oil", "CRUDE_OIL", None),
    "gold": ("Gold", "GOLD", None),
}


def build_institutional_dashboard(
    symbol: str = "NIFTY",
    *,
    option_chain: dict[str, Any] | None = None,
    option_chain_error: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    warnings: list[str] = []
    metrics = {key: _env_metric(label, env_name, unit) for key, (label, env_name, unit) in ENV_METRICS.items()}
    global_indices = _global_indices()
    derivatives = _derivative_metrics(option_chain)

    missing_env = [metric["label"] for metric in metrics.values() if metric["source"] == "unavailable"]
    if missing_env:
        warnings.append(f"Configure institutional inputs for: {', '.join(missing_env)}.")

    if option_chain_error:
        warnings.append(f"Option-chain provider unavailable: {option_chain_error}")
    elif option_chain and option_chain.get("warning"):
        warnings.append(str(option_chain["warning"]))
    if not derivatives["provider_available"]:
        warnings.append("Live option-chain metrics are unavailable; PCR, max pain, and OI leaders are not marked live.")

    return {
        "module": "institutional_dashboard",
        "symbol": symbol,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cash_flows": {
            "fii_cash": metrics["fii_cash"],
            "dii_cash": metrics["dii_cash"],
        },
        "futures": {
            "fii_index_futures": metrics["fii_index_futures"],
        },
        "derivatives": derivatives,
        "macro": {
            "gift_nifty": metrics["gift_nifty"],
            "india_vix": metrics["india_vix"],
            "usd_inr": metrics["usd_inr"],
            "crude_oil": metrics["crude_oil"],
            "gold": metrics["gold"],
        },
        "global_indices": global_indices,
        "market_narrative": _market_narrative(metrics, derivatives, global_indices, warnings),
        "warnings": warnings,
        "data_policy": "Configured values are shown only when provided; unavailable live feeds are never replaced with generated institutional data.",
    }


def _env_metric(label: str, env_name: str, unit: str | None) -> dict[str, Any]:
    value = _env_float(env_name)
    if value is None:
        value = _env_float(f"QUANTGRID_{env_name}")
    return {
        "label": label,
        "value": value,
        "unit": unit,
        "source": "env" if value is not None else "unavailable",
    }


def _global_indices() -> list[dict[str, Any]]:
    raw = os.getenv("GLOBAL_INDICES_JSON") or os.getenv("QUANTGRID_GLOBAL_INDICES_JSON")
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return [{
            "label": "Global Indices",
            "value": None,
            "change_pct": None,
            "source": "invalid-env",
        }]
    if not isinstance(payload, list):
        return []

    indices = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("name") or "").strip()
        if not label:
            continue
        indices.append({
            "label": label,
            "value": _coerce_float(item.get("value")),
            "change_pct": _coerce_float(item.get("change_pct") or item.get("changePct")),
            "source": "env",
        })
    return indices


def _derivative_metrics(option_chain: dict[str, Any] | None) -> dict[str, Any]:
    rows = list(option_chain.get("rows") or []) if isinstance(option_chain, dict) else []
    provider_available = bool(option_chain and option_chain.get("provider_available") and rows)
    highest_call = _highest_oi(rows, "ce")
    highest_put = _highest_oi(rows, "pe")
    return {
        "source": option_chain.get("source") if option_chain else "unavailable",
        "provider_available": provider_available,
        "pcr": option_chain.get("pcr") if provider_available else None,
        "max_pain": option_chain.get("max_pain") if provider_available else None,
        "highest_call_oi": highest_call if provider_available else None,
        "highest_put_oi": highest_put if provider_available else None,
        "oi_change": _oi_change(rows) if provider_available else {"call": None, "put": None, "net": None},
        "updated_at": option_chain.get("updated_at") if option_chain else None,
    }


def _highest_oi(rows: list[dict[str, Any]], side: str) -> dict[str, Any] | None:
    candidates = []
    for row in rows:
        leg = row.get(side) if isinstance(row, dict) else None
        if not isinstance(leg, dict):
            continue
        oi = _coerce_float(leg.get("oi"))
        strike = _coerce_float(row.get("strike"))
        if oi is not None and strike is not None and oi > 0:
            candidates.append({"strike": int(strike), "oi": oi})
    if not candidates:
        return None
    return max(candidates, key=lambda item: item["oi"])


def _oi_change(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    call = _sum_oi_change(rows, "ce")
    put = _sum_oi_change(rows, "pe")
    return {
        "call": call,
        "put": put,
        "net": round((put or 0.0) - (call or 0.0), 2) if call is not None or put is not None else None,
    }


def _sum_oi_change(rows: list[dict[str, Any]], side: str) -> float | None:
    total = 0.0
    seen = False
    for row in rows:
        leg = row.get(side) if isinstance(row, dict) else None
        if not isinstance(leg, dict):
            continue
        value = _coerce_float(
            leg.get("oi_change")
            if leg.get("oi_change") is not None
            else leg.get("change_oi")
            if leg.get("change_oi") is not None
            else leg.get("changeinOpenInterest")
            if leg.get("changeinOpenInterest") is not None
            else leg.get("oiChange")
        )
        if value is None:
            continue
        total += value
        seen = True
    return round(total, 2) if seen else None


def _market_narrative(
    metrics: dict[str, dict[str, Any]],
    derivatives: dict[str, Any],
    global_indices: list[dict[str, Any]],
    warnings: list[str],
) -> str:
    if warnings and not derivatives["provider_available"]:
        return "Institutional dashboard is in watch mode because live option-chain or macro inputs are incomplete."

    fii = metrics["fii_cash"]["value"]
    dii = metrics["dii_cash"]["value"]
    pcr = derivatives["pcr"]
    parts = []
    if fii is not None and dii is not None:
        flow = fii + dii
        parts.append("Domestic and foreign cash flow is net supportive." if flow >= 0 else "Cash market flow is net cautious.")
    if pcr is not None:
        parts.append("Option positioning is put-heavy." if pcr >= 1.1 else "Option positioning is call-heavy." if pcr <= 0.9 else "Option positioning is balanced.")
    if global_indices:
        positive = sum(1 for item in global_indices if (item.get("change_pct") or 0) > 0)
        parts.append("Global index breadth is supportive." if positive >= len(global_indices) / 2 else "Global index breadth is cautious.")
    return " ".join(parts) if parts else "Institutional inputs are waiting for live/configured data."


def _env_float(name: str) -> float | None:
    return _coerce_float(os.getenv(name))


def _coerce_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
