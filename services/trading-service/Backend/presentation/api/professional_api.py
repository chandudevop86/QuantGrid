from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from Backend.app.backtesting.engine import BacktestEngine
from Backend.app.backtesting.report import render_report
from Backend.application.dto import serialize_signal
from Backend.application.paper_trade_store import list_paper_trades, risk_status
from Backend.application.signal_quality import split_signals
from Backend.application.trading_service import TradingService
from Backend.presentation.api.market_api import get_candles
from Backend.presentation.api.roles import require_roles


router = APIRouter(tags=["professional-paper-trading"])


def _clean_candles(response: dict) -> list[dict]:
    candles = list(response.get("candles", []))
    if response.get("volume_status") == "not_reported_for_index":
        return [{**candle, "volume": None} for candle in candles]
    return candles


@router.get("/api/strategies/{strategy}/backtest")
def backtest_strategy(
    strategy: str,
    symbol: str = "NIFTY",
    interval: str = "1m",
    period: str = "1d",
    capital: float = 100_000,
    risk_pct: float = 1,
    rr_ratio: float = 2,
    _role: str = Depends(require_roles("admin", "trader", "analyst")),
):
    candles = _clean_candles(get_candles(symbol, interval=interval, period=period, limit=500))
    result = BacktestEngine().run(
        strategy=strategy,
        symbol=symbol,
        candles=candles,
        capital=capital,
        risk_pct=risk_pct,
        rr_ratio=rr_ratio,
    )
    return render_report(result)


@router.get("/api/trades/paper")
def paper_trades(
    limit: int = Query(default=100, ge=1, le=500),
    _role: str = Depends(require_roles("admin", "trader", "analyst", "viewer", "ops")),
):
    return {"trades": list_paper_trades(limit)}


@router.get("/api/risk/status")
def get_risk_status(_role: str = Depends(require_roles("admin", "trader", "analyst", "viewer", "ops"))):
    status = risk_status()
    status["minimum_score"] = 7
    return status


@router.get("/api/signals/latest")
def latest_signals(
    symbol: str = "NIFTY",
    strategy: str | None = None,
    _role: str = Depends(require_roles("admin", "trader", "analyst", "viewer")),
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
