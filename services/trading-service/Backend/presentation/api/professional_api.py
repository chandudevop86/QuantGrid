from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
import yfinance as yf
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status

from Backend.app.backtesting.engine import BacktestEngine
from Backend.app.backtesting.report import render_report
from Backend.application.dto import serialize_signal
from Backend.application.paper_trade_store import (
    create_trade_journal_entry,
    get_trade_journal_entry,
    list_paper_trades,
    list_trade_journal,
    risk_status,
    update_trade_journal_entry,
)
from Backend.application.candle_validation import validate_live_candle
from Backend.application.monitoring import observe_rejected_signal
from Backend.application.signal_audit import AUDIT_STRATEGIES, StrategyAuditInput, audit_strategy
from Backend.application.signal_quality import split_signals
from Backend.application.signal_validation import validate_signals
from Backend.application.trading_service import TradingService
from Backend.presentation.api.market_api import get_candles, get_price
from Backend.presentation.api.roles import require_roles
from Backend.application.subscriptions import SubscriptionAccess, subscription_access
from pydantic import BaseModel


router = APIRouter(tags=["professional-paper-trading"])
logger = logging.getLogger("quantgrid.professional")


class TradeJournalEntryRequest(BaseModel):
    strategy: str
    signal: str
    symbol: str = "NIFTY"
    status: str = "recorded"
    entry: float | None = None
    entry_price: float | None = None
    stop_loss: float
    target: float
    exit_price: float | None = None
    pnl: float = 0.0
    quantity: int | None = None
    reason: str | None = None
    exit_reason: str | None = None
    source: str = "manual"


class TradeJournalPatchRequest(BaseModel):
    strategy: str | None = None
    signal: str | None = None
    symbol: str | None = None
    status: str | None = None
    entry: float | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    exit_price: float | None = None
    pnl: float | None = None
    quantity: int | None = None
    reason: str | None = None
    exit_reason: str | None = None
    source: str | None = None
    closed_at: str | None = None


def _clean_candles(response: dict) -> list[dict]:
    candles = list(response.get("candles", []))
    if response.get("volume_status") == "not_reported_for_index":
        return [{**candle, "volume": None} for candle in candles]
    return candles


def _sample_backtest_candles(symbol: str, interval: str, limit: int = 160):

    ticker = f"{symbol.upper()}.NS"

    df = yf.download(
        ticker,
        period="6mo",
        interval=interval,
        auto_adjust=False,
        progress=False,
    )

    if df.empty:
        return []

    df = df.tail(limit)

    candles = []

    for ts, row in df.iterrows():

        candles.append({

            "symbol": symbol.upper(),

            "timestamp": ts.isoformat(),

            "open": float(row["Open"]),

            "high": float(row["High"]),

            "low": float(row["Low"]),

            "close": float(row["Close"]),

            "volume": int(row["Volume"]),

            "interval": interval,

        })

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
@router.get("/strategies/{strategy}/backtest", include_in_schema=False)
def backtest_strategy(
    strategy: str,
    symbol: str = "NIFTY",
    interval: str = "1m",
    period: str = "1d",
    start_date: str | None = None,
    end_date: str | None = None,
    capital: float = 100_000,
    risk_pct: float = 2,
    rr_ratio: float = 2,
    max_candles: int = Query(default=200, ge=50, le=1000),
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst")),
):
    try:
       candles = _clean_candles(
        get_candles(
            symbol=symbol,
            interval=interval,
            period=period,
            limit=max_candles,
        )
    )

    except Exception as exc:
       logger.exception(
        "Failed to load historical candles",
        extra={
            "strategy": strategy,
            "symbol": symbol,
            "interval": interval,
            "error": str(exc),
        },
    )

    # Never use fake candles
    raise HTTPException(
        status_code=500,
        detail=f"Unable to fetch historical data: {exc}",
    )

if len(candles) < 50:
    raise HTTPException(
        status_code=400,
        detail="Not enough historical candles available for backtest.",
    )
    candles = _filter_candles_by_date(candles, start_date, end_date)
    candles = candles[-max_candles:]
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
        "max_candles": max_candles,
    }
    return report


@router.get("/api/trades/paper")
@router.get("/trades/paper", include_in_schema=False)
def paper_trades(
    limit: int = Query(default=100, ge=1, le=500),
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
):
    return {"trades": list_paper_trades(limit)}


@router.get("/api/trade-journal")
@router.get("/api/trades/journal")
@router.get("/trade-journal", include_in_schema=False)
@router.get("/trades/journal", include_in_schema=False)
def trade_journal(
    limit: int = Query(default=100, ge=1, le=500),
    strategy: str | None = None,
    status: str | None = None,
    date: str | None = None,
    symbol: str | None = None,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
):
    rows = list_trade_journal(limit, strategy=strategy, status=status, date=date, symbol=symbol)
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


@router.get("/api/trades/journal/{entry_id}")
@router.get("/trades/journal/{entry_id}", include_in_schema=False)
def trade_journal_entry(
    entry_id: int,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
):
    row = get_trade_journal_entry(entry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade journal entry not found.")
    return row


@router.post("/api/trade-journal")
@router.post("/api/trades/journal")
@router.post("/trade-journal", include_in_schema=False)
@router.post("/trades/journal", include_in_schema=False)
def create_trade_journal(
    payload: TradeJournalEntryRequest,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst")),
):
    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    if payload_data.get("entry") is None and payload_data.get("entry_price") is not None:
        payload_data["entry"] = payload_data["entry_price"]
    if payload_data.get("entry") is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="entry_price is required.")
    return create_trade_journal_entry(payload_data)


@router.patch("/api/trades/journal/{entry_id}")
@router.patch("/trades/journal/{entry_id}", include_in_schema=False)
def patch_trade_journal(
    entry_id: int,
    payload: TradeJournalPatchRequest,
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst")),
):
    payload_data = payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else payload.dict(exclude_none=True)
    try:
        return update_trade_journal_entry(entry_id, payload_data)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade journal entry not found.") from exc


@router.get("/api/risk/status")
@router.get("/risk/status", include_in_schema=False)
def get_risk_status(_role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops"))):
    status = risk_status()
    status["minimum_score"] = 7
    return status


def _empty_signals(symbol: str, *, reason: str | None = None) -> dict:
    return {
        "symbol": symbol.upper(),
        "active_signals": [],
        "rejected_signals": [],
        "stale_signals": [],
        "latest_candle_time": None,
        "status": "empty",
        "message": reason or "No signals available yet.",
    }


@router.get("/api/signals")
@router.get("/api/signals/latest")
@router.get("/signals", include_in_schema=False)
@router.get("/signals/latest", include_in_schema=False)
def latest_signals(
    symbol: str = "NIFTY",
    strategy: str | None = None,
    access: SubscriptionAccess = Depends(subscription_access),
):
    try:
        one_minute = _clean_candles(get_candles(symbol, interval="1m", period="1d", limit=100))
        five_minute = _clean_candles(get_candles(symbol, interval="5m", period="1d", limit=100))
        fifteen_minute = _clean_candles(get_candles(symbol, interval="15m", period="1d", limit=100))
    except Exception as exc:
        logger.exception("latest_signals_candle_load_failed", extra={"symbol": symbol, "error_type": exc.__class__.__name__})
        return _empty_signals(symbol, reason="Market candles are unavailable; no signals generated.")
    try:
        service = TradingService()
    except Exception as exc:
        logger.exception("latest_signals_service_init_failed", extra={"error_type": exc.__class__.__name__})
        return _empty_signals(symbol, reason=f"Trading service is unavailable ({exc.__class__.__name__}); no signals generated.")
    strategies = [strategy] if strategy else service.trading_engine.strategy_engine.available()
    if not access.can("strategy.multiple"):
        strategies = strategies[:1]

    active = []
    rejected = []
    stale = []
    for item in strategies:
        try:
            raw = service.run_strategy(
                strategy_name=item,
                data=one_minute,
                symbol=symbol.upper(),
                capital=100_000,
                risk_pct=2,
                rr_ratio=2,
                params={"mtf_candles": five_minute, "htf_candles": fifteen_minute},
            )
        except Exception as exc:
            logger.exception("latest_signals_strategy_failed", extra={"strategy": item, "error_type": exc.__class__.__name__})
            rejected.append({"signal": {"strategy_name": item, "signal": "ERROR"}, "decision": {"reason": str(exc), "score": 0}})
            observe_rejected_signal(item, exc.__class__.__name__)
            continue
        active_signals, rejected_signals, stale_signals = split_signals(
            raw,
            candles_1m=one_minute,
            candles_15m=fifteen_minute,
        )
        for signal_obj in active_signals:
            serialized_signal = serialize_signal(signal_obj)
            active.append(serialized_signal)
            create_trade_journal_entry(
                {
                    "strategy": serialized_signal.get("strategy_name"),
                    "signal": serialized_signal.get("signal"),
                    "symbol": serialized_signal.get("symbol"),
                    "status": "accepted_signal",
                    "entry": serialized_signal.get("entry_price") or serialized_signal.get("entry"),
                    "stop_loss": serialized_signal.get("stop_loss"),
                    "target": serialized_signal.get("target_price") or serialized_signal.get("target"),
                    "quantity": serialized_signal.get("quantity"),
                    "reason": serialized_signal.get("reason"),
                    "source": "signal_scan",
                    "created_at": serialized_signal.get("timestamp"),
                }
            )
        for entry in rejected_signals:
            serialized = {"signal": serialize_signal(entry["signal"]), "decision": entry["decision"]}
            rejected.append(serialized)
            observe_rejected_signal(serialized["signal"].get("strategy_name"), serialized["decision"].get("reason"))
            create_trade_journal_entry(
                {
                    "strategy": serialized["signal"].get("strategy_name"),
                    "signal": serialized["signal"].get("signal"),
                    "symbol": serialized["signal"].get("symbol"),
                    "status": "rejected_signal",
                    "entry": serialized["signal"].get("entry_price") or serialized["signal"].get("entry"),
                    "stop_loss": serialized["signal"].get("stop_loss"),
                    "target": serialized["signal"].get("target_price") or serialized["signal"].get("target"),
                    "quantity": serialized["signal"].get("quantity"),
                    "reason": serialized["decision"].get("reason"),
                    "source": "signal_scan",
                    "created_at": serialized["signal"].get("timestamp"),
                }
            )
        stale.extend(
            {"signal": serialize_signal(entry["signal"]), "decision": entry["decision"]}
            for entry in stale_signals
        )

    limit = access.limit("signals_history_limit") or 5
    remaining = limit
    limited_active = active[:remaining]
    remaining -= len(limited_active)
    limited_rejected = rejected[:remaining]
    remaining -= len(limited_rejected)
    limited_stale = stale[:remaining]
    return {
        "symbol": symbol.upper(),
        "active_signals": limited_active,
        "rejected_signals": limited_rejected,
        "stale_signals": limited_stale,
        "history_limit": limit,
        "latest_candle_time": one_minute[-1]["timestamp"] if one_minute else None,
    }


@router.get("/api/signals/audit")
@router.get("/signals/audit", include_in_schema=False)
def signals_audit(
    symbol: str = "NIFTY",
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
):
    return _build_signal_audit(symbol)


@router.get("/api/system/audit")
@router.get("/system/audit", include_in_schema=False)
def system_audit(
    symbol: str = "NIFTY",
    _role: str = Depends(require_roles("admin", "developer", "trader", "analyst", "viewer", "ops")),
):
    issues: list[str] = []
    price_payload: dict | None = None
    price_source = "unavailable"
    try:
        price_payload = get_price(symbol)
        price_source = str(price_payload.get("source") or price_payload.get("provider") or "unknown")
    except Exception as exc:
        logger.exception("system_audit_price_failed", extra={"symbol": symbol, "error_type": exc.__class__.__name__})
        issues.append(f"Market price unavailable: {exc}")

    signal_audit = _build_signal_audit(symbol)
    data = signal_audit.get("data", {})
    lifecycle = signal_audit["lifecycle_totals"]
    using_fallback = _is_fallback_source(price_source) or bool(data.get("using_fallback_data"))
    candle_count = int(data.get("candle_count") or 0)
    candle_age = data.get("candle_age_seconds")
    data_ok = bool(price_payload and float(price_payload.get("price") or price_payload.get("ltp") or 0) > 0)
    data_ok = data_ok and candle_count >= 20 and not using_fallback and bool(data.get("valid_for_analysis"))
    logic_ok = bool(signal_audit["strategies"]) and any(int(row.get("raw_signal_count") or 0) >= 0 for row in signal_audit["strategies"])
    if not price_payload:
        issues.append("Market price check failed.")
    if candle_count < 20:
        issues.append(f"Only {candle_count} candles available; strategies need enough historical context.")
    if using_fallback:
        issues.append("Fallback/sample/cached market data is in use.")
    if not data.get("valid_for_analysis"):
        issues.append("Candles are not valid for analysis.")
    if int(lifecycle["RAW_SIGNAL"]) == 0:
        issues.append("Strategies ran but generated no raw signals.")
    if int(lifecycle["VALIDATED_SIGNAL"]) == 0:
        issues.append("No validated signals passed the confirmation gates.")
    if int(lifecycle["PAPER_TRADE_CREATED"]) == 0:
        issues.append(_trade_block_reason(signal_audit["strategies"], data))

    return {
        "data_status": "OK" if data_ok else "ISSUES",
        "data_ok": data_ok,
        "logic_ok": logic_ok,
        "market_price": price_payload,
        "candle_count": candle_count,
        "candle_age_seconds": candle_age,
        "using_fallback_data": using_fallback,
        "strategies_working": {
            "checked": len(signal_audit["strategies"]),
            "with_raw_signals": sum(1 for row in signal_audit["strategies"] if int(row.get("raw_signal_count") or 0) > 0),
            "with_validated_signals": sum(1 for row in signal_audit["strategies"] if int(row.get("validated_signal_count") or 0) > 0),
            "all_strategy_rows_returned": len(signal_audit["strategies"]) == len(AUDIT_STRATEGIES),
        },
        "raw_signals": lifecycle["RAW_SIGNAL"],
        "validated_signals": lifecycle["VALIDATED_SIGNAL"],
        "rejected_signals": lifecycle["REJECTED_SIGNAL"],
        "trades_created": lifecycle["PAPER_TRADE_CREATED"],
        "trade_not_created_because": _trade_block_reason(signal_audit["strategies"], data),
        "issues": issues,
        "signal_audit": signal_audit,
    }


def _build_signal_audit(symbol: str = "NIFTY") -> dict:
    try:
        candles_response = get_candles(symbol, interval="1m", period="1d", limit=150)
        confirmation_response = get_candles(symbol, interval="5m", period="1d", limit=150)
        trend_response = get_candles(symbol, interval="15m", period="1d", limit=150)
        one_minute = _clean_candles(candles_response)
        five_minute = _clean_candles(confirmation_response)
        fifteen_minute = _clean_candles(trend_response)
    except Exception as exc:
        logger.exception("signal_audit_candle_load_failed", extra={"symbol": symbol, "error_type": exc.__class__.__name__})
        candles_response, confirmation_response, trend_response = {}, {}, {}
        one_minute, five_minute, fifteen_minute = [], [], []

    try:
        service = TradingService()
    except Exception as exc:
        logger.exception("signal_audit_service_init_failed", extra={"symbol": symbol, "error_type": exc.__class__.__name__})
        return {
            "symbol": symbol.upper(),
            "latest_candle_time": one_minute[-1]["timestamp"] if one_minute else None,
            "data": {"candle_source": candles_response.get("source")},
            "strategies": [],
            "lifecycle_totals": {},
            "error": f"Trading service is unavailable ({exc.__class__.__name__}); signal audit could not run.",
        }
    paper_trades = list_paper_trades(500)
    candle_source = candles_response.get("source")
    candle_validation = validate_live_candle(
        one_minute,
        interval="1m",
        mode="paper",
        source=candle_source,
        provider_fetched_at=candles_response.get("fetched_at"),
    ) if one_minute else None
    rows = []
    totals = {
        "RAW_SIGNAL": 0,
        "VALIDATED_SIGNAL": 0,
        "ACCEPTED_SIGNAL": 0,
        "REJECTED_SIGNAL": 0,
        "PAPER_TRADE_CREATED": 0,
    }
    for key, label in AUDIT_STRATEGIES:
        raw_signals = []
        validated_signals = []
        try:
            raw_signals = service.run_strategy(
                strategy_name=key,
                data=one_minute,
                symbol=symbol.upper(),
                capital=100_000,
                risk_pct=2,
                rr_ratio=2,
                params={
                    "mtf_candles": five_minute,
                    "htf_candles": fifteen_minute,
                    "m15_candles": fifteen_minute,
                    "m5_candles": five_minute,
                    "h1_candles": fifteen_minute,
                    "h4_candles": fifteen_minute,
                    "daily_candles": fifteen_minute,
                },
            ) if one_minute else []
            validated_signals, _data_source = validate_signals(
                raw_signals,
                symbol=symbol,
                candles=one_minute,
                candle_source=candle_source,
            ) if one_minute else ([], "cached")
        except Exception as exc:
            logger.exception("signal_audit_strategy_failed", extra={"strategy": key, "error_type": exc.__class__.__name__})
        paper_count = sum(
            1
            for trade in paper_trades
            if str(trade.get("strategy") or "").strip().lower() in {key, label.lower(), label.replace(" ", "_").lower()}
        )
        row = audit_strategy(
            StrategyAuditInput(
                key=key,
                label=label,
                raw_signals=raw_signals,
                validated_signals=validated_signals,
                candles=one_minute,
                trend_candles=fifteen_minute,
                candle_source=candle_source,
                candle_validation=candle_validation,
                execution_mode="paper",
                paper_trade_created_count=paper_count,
            )
        )
        rows.append(row)
        for lifecycle_key, value in row["lifecycle"].items():
            totals[lifecycle_key] += int(value or 0)

    return {
        "symbol": symbol.upper(),
        "latest_candle_time": one_minute[-1]["timestamp"] if one_minute else None,
        "data": {
            "candle_source": candle_source,
            "confirmation_source": confirmation_response.get("source"),
            "trend_source": trend_response.get("source"),
            "candle_count": len(one_minute),
            "candle_age_seconds": getattr(candle_validation, "delay_seconds", None),
            "valid_for_analysis": bool(getattr(candle_validation, "valid_for_analysis", False)),
            "valid_for_execution": bool(getattr(candle_validation, "valid_for_execution", False)),
            "market_status": getattr(candle_validation, "market_status", None),
            "using_fallback_data": any(
                _is_fallback_source(source)
                for source in (candle_source, confirmation_response.get("source"), trend_response.get("source"))
            ),
        },
        "strategies": rows,
        "lifecycle_totals": totals,
        "rejection_reasons": [
            "NEUTRAL",
            "LOW_CONFIDENCE",
            "MISSING_RISK_REWARD",
            "STALE_CANDLE",
            "MARKET_CLOSED",
            "RISK_REJECTED",
            "MAX_TRADES_REACHED",
            "MISSING_STOP_LOSS",
            "MISSING_TARGET",
        ],
    }


def _is_fallback_source(source: str | None) -> bool:
    return str(source or "").strip().lower() in {"sample", "sample-fallback", "stored-live-cache", "cached", "demo"}


def _trade_block_reason(strategies: list[dict], data: dict) -> str:
    if not data.get("valid_for_execution"):
        status = data.get("market_status") or "market data not executable"
        return f"Market data is not executable: {status}."
    if not strategies:
        return "No strategy audit rows were returned."
    if sum(int(row.get("raw_signal_count") or 0) for row in strategies) == 0:
        return "No strategy generated a raw signal."
    if sum(int(row.get("validated_signal_count") or 0) for row in strategies) == 0:
        reasons = [row.get("rejection_reason") for row in strategies if row.get("rejection_reason")]
        reason = next((item for item in reasons if item != "NEUTRAL"), None) or "signals did not pass validation"
        return f"No validated signal passed: {reason}."
    blocking = next((row for row in strategies if row.get("rejection_reason") and row.get("rejection_reason") != "NEUTRAL"), None)
    if blocking:
        return f"{blocking.get('strategy')} blocked by {blocking.get('rejection_reason')}."
    return "Validated signal is ready, but no paper order has been submitted yet."
