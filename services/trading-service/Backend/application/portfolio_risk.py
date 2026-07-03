from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from Backend.application.market_data_store import latest_candles
from Backend.application.paper_trade_store import list_trade_journal, risk_status
from Backend.application.position_store import list_open_positions, position_summary


def build_portfolio_risk_dashboard(
    symbol: str = "NIFTY",
    *,
    entry_price: float | None = None,
    stop_loss: float | None = None,
    atr_multiplier: float = 1.5,
) -> dict[str, Any]:
    symbol = symbol.upper()
    risk = risk_status()
    positions = position_summary()
    open_positions = list_open_positions()
    journal = list_trade_journal(500)
    capital = float(risk.get("capital") or 0.0)
    current_exposure = float(risk.get("current_exposure") or positions.get("current_exposure") or 0.0)
    max_exposure = _env_float("QUANTGRID_MAX_EXPOSURE", capital * 1.5 if capital else 0.0)
    atr = _atr(symbol)
    entry = entry_price or _latest_close(symbol) or _avg_open_entry(open_positions) or 0.0
    stop = stop_loss if stop_loss is not None else _default_stop(entry, atr, atr_multiplier)
    sizing = _position_sizing(
        capital=capital,
        risk_pct=float(risk.get("risk_per_trade_pct") or 0.0),
        entry=entry,
        stop_loss=stop,
        atr=atr,
        atr_multiplier=atr_multiplier,
    )
    pnl = _period_pnl(journal, unrealized=float(positions.get("unrealized_pnl") or 0.0), daily_pnl=float(risk.get("daily_pnl") or 0.0))
    exposure = {
        "current": round(current_exposure, 2),
        "limit": round(max_exposure, 2),
        "available": round(max(max_exposure - current_exposure, 0.0), 2),
        "utilization_pct": round(current_exposure / max_exposure * 100, 2) if max_exposure > 0 else 0.0,
    }
    limits = {
        "daily_loss_limit": risk.get("max_daily_loss"),
        "daily_loss_remaining": round(max(float(risk.get("max_daily_loss") or 0.0) + min(float(risk.get("daily_pnl") or 0.0), 0.0), 0.0), 2),
        "max_trades_per_day": risk.get("max_trades_per_day"),
        "trades_today": risk.get("trades_today"),
        "max_open_trades": risk.get("max_open_positions"),
        "open_trades": risk.get("open_positions"),
        "max_exposure": round(max_exposure, 2),
        "max_quantity": risk.get("max_quantity"),
        "risk_per_trade_pct": risk.get("risk_per_trade_pct"),
        "risk_per_trade_amount": risk.get("risk_per_trade_amount"),
    }
    checks = {
        "daily_loss": float(risk.get("daily_pnl") or 0.0) > -float(risk.get("max_daily_loss") or 0.0),
        "max_open_trades": int(risk.get("open_positions") or 0) < int(risk.get("max_open_positions") or 0),
        "max_trades_per_day": int(risk.get("trades_today") or 0) < int(risk.get("max_trades_per_day") or 0),
        "exposure_limit": current_exposure <= max_exposure if max_exposure > 0 else True,
        "risk_configured": bool(risk.get("risk_configured")),
    }
    return {
        "module": "portfolio_risk",
        "symbol": symbol,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pnl": pnl,
        "position_sizing": sizing,
        "limits": limits,
        "exposure": exposure,
        "checks": checks,
        "positions": {
            **positions,
            "open": open_positions,
        },
        "risk_status": risk,
        "state": "blocked" if not all(checks.values()) else "normal",
    }


def _period_pnl(journal: list[dict[str, Any]], *, unrealized: float, daily_pnl: float) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)
    realized_week = 0.0
    realized_month = 0.0
    for row in journal:
        timestamp = _row_time(row)
        if timestamp is None:
            continue
        pnl = float(row.get("pnl") or 0.0)
        if timestamp >= week_start:
            realized_week += pnl
        if timestamp >= month_start:
            realized_month += pnl
    return {
        "daily": round(daily_pnl, 2),
        "weekly": round(realized_week + unrealized, 2),
        "monthly": round(realized_month + unrealized, 2),
        "unrealized": round(unrealized, 2),
        "basis": "journal_realized_plus_open_unrealized",
    }


def _position_sizing(
    *,
    capital: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
    atr: float | None,
    atr_multiplier: float,
) -> dict[str, Any]:
    risk_amount = max(capital, 0.0) * (risk_pct / 100.0)
    fixed_risk_per_unit = abs(entry - stop_loss)
    atr_risk_per_unit = (atr or 0.0) * max(float(atr_multiplier), 0.0)
    fixed_size = int(risk_amount // fixed_risk_per_unit) if fixed_risk_per_unit > 0 else 0
    atr_size = int(risk_amount // atr_risk_per_unit) if atr_risk_per_unit > 0 else 0
    return {
        "capital": round(capital, 2),
        "entry_price": round(entry, 2),
        "stop_loss": round(stop_loss, 2),
        "fixed_risk": {
            "risk_amount": round(risk_amount, 2),
            "risk_per_unit": round(fixed_risk_per_unit, 2),
            "quantity": fixed_size,
        },
        "atr_based": {
            "atr": round(atr, 2) if atr is not None else None,
            "atr_multiplier": atr_multiplier,
            "risk_per_unit": round(atr_risk_per_unit, 2),
            "quantity": atr_size,
        },
    }


def _atr(symbol: str, period: int = 14) -> float | None:
    candles = latest_candles(symbol, "1m", period + 1) or latest_candles(symbol, "5m", period + 1)
    if len(candles) < 2:
        return _env_float("QUANTGRID_ATR_FALLBACK", None)
    ranges = []
    previous_close = float(candles[0].get("close") or 0.0)
    for candle in candles[1:]:
        high = float(candle.get("high") or 0.0)
        low = float(candle.get("low") or 0.0)
        close = float(candle.get("close") or previous_close)
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = close
    return sum(ranges[-period:]) / min(len(ranges), period) if ranges else None


def _latest_close(symbol: str) -> float | None:
    candles = latest_candles(symbol, "1m", 1) or latest_candles(symbol, "5m", 1)
    if not candles:
        return None
    try:
        return float(candles[-1].get("close"))
    except (TypeError, ValueError):
        return None


def _avg_open_entry(open_positions: list[dict[str, Any]]) -> float | None:
    values = [float(item.get("entry_price") or 0.0) for item in open_positions if float(item.get("entry_price") or 0.0) > 0]
    return sum(values) / len(values) if values else None


def _default_stop(entry: float, atr: float | None, atr_multiplier: float) -> float:
    if entry <= 0:
        return 0.0
    distance = (atr or max(entry * 0.005, 1.0)) * max(float(atr_multiplier), 0.1)
    return max(entry - distance, 0.0)


def _row_time(row: dict[str, Any]) -> datetime | None:
    raw = row.get("closed_at") or row.get("created_at") or row.get("timestamp")
    if raw in {None, ""}:
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _env_float(name: str, default: float | None) -> float | None:
    raw = os.getenv(name)
    if raw in {None, ""}:
        return default
    try:
        return float(raw)
    except ValueError:
        return default
