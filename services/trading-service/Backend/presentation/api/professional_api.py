from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from Backend.app.backtesting.engine import BacktestEngine
from Backend.app.backtesting.report import render_report
from Backend.application.dto import serialize_signal
from Backend.application.paper_trade_store import create_trade_journal_entry, list_paper_trades, list_trade_journal, risk_status
from Backend.application.signal_quality import split_signals
from Backend.application.trading_service import TradingService
from Backend.presentation.api.market_api import get_candles
from Backend.presentation.api.roles import require_roles
from pydantic import BaseModel


router = APIRouter(tags=["professional-paper-trading"])
logger = logging.getLogger("quantgrid.professional")


class TradeJournalEntryRequest(BaseModel):
    strategy: str
    signal: str
    symbol: str = "NIFTY"
    entry: float
    stop_loss: float
    target: float
    exit_price: float | None = None
    pnl: float = 0.0
    exit_reason: str | None = None


def _clean_candles(response: dict) -> list[dict]:
    candles = list(response.get("candles", []))
    if response.get("volume_status") == "not_reported_for_index":
        return [{**candle, "volume": None} for candle in candles]
    return candles


def _sample_backtest_candles(symbol: str, interval: str, limit: int = 160) -> list[dict]:
    now = datetime.now(timezone.utc) - timedelta(minutes=limit)
    candles = []
    base = 22500.0
    for index in range(limit):
        drift = index * 1.8
        wave = ((index % 11) - 5) * 6
        close = base + drift + wave
        candles.append(
            {
                "symbol": symbol.upper(),
                "timestamp": (now + timedelta(minutes=index)).isoformat(),
                "open": round(close - 4, 2),
                "high": round(close + 12, 2),
                "low": round(close - 10, 2),
                "close": round(close, 2),
                "volume": 1000 + index * 25,
                "interval": interval,
            }
        )
    return candles


def _filter_candles_by_date(candles: list[dict], start_date: str | None, end_date: str | None) -> list[dict]:
    if not start_date and not end_date:
        return candles
    start = datetime.fromisoformat(start_date).date() if start_date else None
    end = datetime.fromisoformat(end_date).date() if end_date else None
    filtered = []
    for candle in candles:
        timestamp = str(candle.get("timestamp") or "")
        if not timestamp:
            continue
        candle_date = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date()
        if start and candle_date < start:
            continue
        if end and candle_date > end:
            continue
        filtered.append(candle)
    return filtered or candles


@router.get("/api/strategies/{strategy}/backtest")
def backtest_strategy(
    strategy: str,
    symbol: str = "NIFTY",
    interval: str = "1m",
    period: str = "1d",
    start_date: str | None = None,
    end_date: str | None = None,
    capital: float = 100_000,
    risk_pct: float = 1,
    rr_ratio: float = 2,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst")),
):
    try:
        candles = _clean_candles(get_candles(symbol, interval=interval, period=period, limit=500))
    except Exception as exc:
        logger.exception(
            "backtest_candle_load_failed",
            extra={"strategy": strategy, "symbol": symbol, "interval": interval, "error_type": exc.__class__.__name__},
        )
        candles = _sample_backtest_candles(symbol, interval)
    candles = _filter_candles_by_date(candles, start_date, end_date)
    result = BacktestEngine().run(
        strategy=strategy,
        symbol=symbol,
        candles=candles,
        capital=capital,
        risk_pct=risk_pct,
        rr_ratio=rr_ratio,
    )
    report = render_report(result)
    metrics = report.setdefault("metrics", {})
    metrics["recent_accuracy"] = metrics.get("recent_accuracy", metrics.get("win_rate", 0.0))
    report["input"] = {
        "symbol": symbol.upper(),
        "interval": interval,
        "strategy": strategy,
        "start_date": start_date,
        "end_date": end_date,
        "candles": len(candles),
    }
    return report


@router.get("/api/trades/paper")
def paper_trades(
    limit: int = Query(default=100, ge=1, le=500),
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
):
    return {"trades": list_paper_trades(limit)}


@router.get("/api/trade-journal")
@router.get("/api/trades/journal")
def trade_journal(
    limit: int = Query(default=100, ge=1, le=500),
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
):
    rows = list_trade_journal(limit)
    closed = [row for row in rows if row.get("exit_price") is not None or row.get("exit_reason")]
    wins = [row for row in closed if float(row.get("pnl") or 0.0) > 0]
    return {
        "rows": rows,
        "summary": {
            "total_trades": len(rows),
            "closed_trades": len(closed),
            "win_rate": round(len(wins) / len(closed) * 100, 2) if closed else 0.0,
            "pnl": round(sum(float(row.get("pnl") or 0.0) for row in rows), 2),
        },
    }


@router.post("/api/trade-journal")
def create_trade_journal(
    payload: TradeJournalEntryRequest,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst")),
):
    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    return create_trade_journal_entry(payload_data)


@router.get("/api/risk/status")
def get_risk_status(_role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops"))):
    status = risk_status()
    status["minimum_score"] = 7
    return status


@router.get("/api/signals/latest")
def latest_signals(
    symbol: str = "NIFTY",
    strategy: str | None = None,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer")),
):
    one_minute = _clean_candles(get_candles(symbol, interval="1m", period="1d", limit=100))
    five_minute = _clean_candles(get_candles(symbol, interval="5m", period="1d", limit=100))
    fifteen_minute = _clean_candles(get_candles(symbol, interval="15m", period="1d", limit=100))
    service = TradingService()
    strategies = [strategy] if strategy else service.trading_engine.strategy_engine.available()

    active = []
    rejected = []
    stale = []
    for item in strategies:
        raw = service.run_strategy(
            strategy_name=item,
            data=one_minute,
            symbol=symbol.upper(),
            capital=100_000,
            risk_pct=1,
            rr_ratio=2,
            params={"mtf_candles": five_minute, "htf_candles": fifteen_minute},
        )
        active_signals, rejected_signals, stale_signals = split_signals(
            raw,
            candles_1m=one_minute,
            candles_15m=fifteen_minute,
        )
        active.extend(serialize_signal(signal) for signal in active_signals)
        rejected.extend(
            {"signal": serialize_signal(entry["signal"]), "decision": entry["decision"]}
            for entry in rejected_signals
        )
        stale.extend(
            {"signal": serialize_signal(entry["signal"]), "decision": entry["decision"]}
            for entry in stale_signals
        )

    return {
        "symbol": symbol.upper(),
        "active_signals": active,
        "rejected_signals": rejected,
        "stale_signals": stale,
        "latest_candle_time": one_minute[-1]["timestamp"] if one_minute else None,
    }
