from __future__ import annotations
from time import sleep
import json
import logging
from datetime import datetime, timezone
from math import erf, exp, log, sqrt
from statistics import mean
from typing import Any
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from Backend.application.kill_switch import kill_switch_status
from Backend.application.market_data_store import latest_candles, latest_price_tick
from Backend.application.monitoring import observe_option_chain_failure
from Backend.application.paper_trade_store import list_paper_trades, risk_status
from Backend.trading_system.backtesting import BacktestEngine
from Backend.trading_system.risk import GlobalRiskManager
from Backend.trading_system.slippage import SlippageConfig, SlippageModel
from Backend.application.providers.nse_playwright import fetch_nse_option_chain
from typing import Any, Dict, List, cast
logger = logging.getLogger("quantgrid.option_chain")



def _round_to_step(value: float, step: int) -> int:
    return int(round(value / step) * step)


def _latest_underlying_price(symbol: str, fallback: float | None = None) -> float:
    tick = latest_price_tick(symbol)
    if tick and tick.get("price") is not None:
        return float(tick["price"])
    candles = latest_candles(symbol, "1m", 1) or latest_candles(symbol, "5m", 1)
    if candles:
        close = candles[-1].get("close")
        if close is not None:
            return float(close)
    if fallback is not None:
        return fallback
    raise RuntimeError(f"No stored provider price is available for {symbol.upper()}.")









            
def option_chain_engine(
                symbol: str = "NIFTY",
                *,
                strikes_each_side: int = 5,
                step: int = 50,
                ) -> dict[str, Any]:
                return _option_chain_compat_payload(
                
                {
                "module": "option_chain_engine",
                "symbol": symbol.upper(),
                "underlying_price": None,
                "atm_strike": None,
                "expiry": None,
                "step": max(1, int(step)),
                "source": "option-chain-unavailable",
                "synthetic": False,
                "provider_available": False,
                "provider_warning": (
                    "Synthetic option-chain generation is disabled. "
                    "Use a live option-chain provider."
                ),
                "pcr": None,
                "max_pain": None,
                "greek_model": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "rows": [],
            }
        )

def historical_option_chain(symbol: str = "NIFTY", *, periods: int = 12, step: int = 50) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "module": "historical_option_chain",
            "symbol": symbol.upper(),
            "source": "historical-option-chain-unavailable",
            "interval": "5m",
            "snapshots": [],
            "provider_available": False,
            "warning": "Synthetic history is disabled. Historical snapshots will appear after live option-chain storage is configured.",
            "updated_at": now.isoformat(),
        }


def _stored_provider_candles(symbol: str) -> list[dict[str, Any]]:
        return latest_candles(symbol, "5m", 160)


def backtesting_module(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    symbol = str(payload.get("symbol") or "NIFTY").upper()
    capital = float(payload.get("capital") or 100000)
    candles = payload.get("candles") or _stored_provider_candles(symbol)
    if not candles:
        raise ValueError(f"Backtest requires provider-backed candles for {symbol}; synthetic candle generation is disabled.")
    max_candles = int(payload.get("max_candles") or 0)
    if max_candles > 0 and len(candles) > max_candles:
        candles = candles[-max_candles:]
    cost_model = _backtest_cost_model(payload)
    effective_slippage_bps = cost_model["slippage_bps"] + cost_model["spread_bps"] / 2.0
    engine = BacktestEngine(
        risk_manager=GlobalRiskManager(),
        slippage_model=SlippageModel(
            SlippageConfig(
                mode="fixed",
                fixed_bps=effective_slippage_bps,
                max_slippage_bps=max(effective_slippage_bps, 0.0),
            )
        ),
        brokerage_per_order=cost_model["brokerage_per_order"],
        brokerage_bps=cost_model["brokerage_bps"],
        taxes_bps=cost_model["taxes_bps"],
        latency_ms=cost_model["entry_delay_seconds"] * 1000
    )
    result = engine.run(
        candles=candles,
        strategy_name=str(payload.get("strategy_name") or "amd"),
        symbol=symbol,
        capital=capital,
        risk_pct=float(payload.get("risk_pct") or 1.0),
        rr_ratio=float(payload.get("rr_ratio") or 2.0),
        min_score=float(payload.get("min_score") or 0.0),
    ).to_dict()
    trades = result.get("trades", [])
    equity = capital
    curve = [{"index": 0, "equity": round(equity, 2)}]
    for index, trade in enumerate(trades, start=1):
        equity += float(trade.get("pnl") or 0.0)
        curve.append({"index": index, "equity": round(equity, 2), "time": trade.get("exit_time")})
    metrics = {
        key: result.get(key)
        for key in (
            "total_trades",
            "win_rate",
            "gross_pnl",
            "total_costs",
            "net_pnl",
            "pnl",
            "expectancy",
            "max_drawdown",
            "sharpe_ratio",
            "rejected_signal_count",
            "rejection_reasons",
            "average_latency_ms",
        )
    }
    metrics.update(_professional_backtest_metrics(candles, trades, curve, capital))
    return {
        "module": "backtesting",
        "symbol": symbol,
        "payload": {key: value for key, value in payload.items() if key != "candles"} | {"candles": len(candles)},
        "metrics": metrics,
        "cost_model": cost_model,
        "equity_curve": curve,
        "recent_outcomes": trades[-10:],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def backtesting_comparison(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        strategies = payload.get("strategies") or ["amd", "breakout", "btst", "cbt", "crt_tbs", "mean_reversion", "mtf", "mtfa", "supply_demand"]
        normalized = [str(strategy).strip().lower() for strategy in strategies if str(strategy).strip()]
        if not normalized:
            normalized = ["amd"]
        runs = []
        for strategy in normalized[:12]:
            run_payload = {**payload, "strategy_name": strategy}
            run_payload.pop("strategies", None)
            result = backtesting_module(run_payload)
            metrics = result.get("metrics", {})
            runs.append({
                "strategy": strategy,
                "symbol": result.get("symbol"),
                "metrics": metrics,
                "cost_model": result.get("cost_model", {}),
                "equity_curve": result.get("equity_curve", []),
                "recent_outcomes": result.get("recent_outcomes", []),
            })
        ranked = sorted(runs, key=_backtest_rank_key, reverse=True)
        return {
            "module": "backtesting_comparison",
            "symbol": str(payload.get("symbol") or "NIFTY").upper(),
            "runs": runs,
            "ranked": ranked,
            "best_strategy": ranked[0]["strategy"] if ranked else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }



def _backtest_rank_key(item: dict[str, Any]) -> tuple[float, float, float, float]:
        metrics = item.get("metrics", {}) or {}
        total_trades = float(metrics.get("total_trades") or 0)
        return (
            1.0 if total_trades > 0 else 0.0,
            float(metrics.get("sharpe_ratio") or 0),
            float(metrics.get("net_pnl") or metrics.get("pnl") or 0),
            -float(metrics.get("max_drawdown") or 0),
        )
def _professional_backtest_metrics(
        candles: list[dict[str, Any]],
        trades: list[dict[str, Any]],
        equity_curve: list[dict[str, Any]],
        capital: float,
        ) -> dict[str, Any]:
        pnls = [float(trade.get("pnl") or 0.0) for trade in trades]
        wins = [pnl for pnl in pnls if pnl > 0]
        losses = [pnl for pnl in pnls if pnl < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        final_equity = float(equity_curve[-1]["equity"]) if equity_curve else capital
        net_pnl = final_equity - capital
        total_return_pct = net_pnl / max(capital, 1.0) * 100.0
        period_years = _backtest_period_years(candles)
        cagr = ((final_equity / max(capital, 1.0)) ** (1 / period_years) - 1) * 100 if period_years and final_equity > 0 else 0.0
        return {
            "cagr": round(float(cagr), 2),
            "total_return_pct": round(float(total_return_pct), 2),
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else round(gross_profit, 2) if gross_profit else 0.0,
            "average_profit": round(sum(wins) / len(wins), 2) if wins else 0.0,
            "average_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
            "average_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
            "win_rate_pct": round(len(wins) / len(pnls) * 100, 2) if pnls else 0.0,
            "period_years": round(period_years, 4),
            "starting_equity": round(capital, 2),
            "ending_equity": round(final_equity, 2),
        }


from typing import Any

def _backtest_cost_model(payload: dict[str, Any]) -> dict[str, Any]:
# 1. Parse your numeric values into explicit float variables first
        slippage = float(payload.get("slippage_bps", 5.0))
        spread = float(payload.get("spread_bps", 8.0))

# 2. Compute your calculated metric cleanly using standard math
        effective_slippage = slippage + (spread / 2.0)

        model = {
            "brokerage_per_order": float(payload.get("brokerage_per_order", 20.0)),
            "brokerage_bps": float(payload.get("brokerage_bps", 0.0)),
            "taxes_bps": float(payload.get("taxes_bps", 2.5)),
            "slippage_bps": slippage,
            "spread_bps": spread,
            "entry_delay_seconds": int(payload.get("entry_delay_seconds", 60)),
            "candle_confirmation": bool(payload.get("candle_confirmation", True)),
            "gap_opening_policy": str(payload.get("gap_opening_policy") or "skip first candle after large gap"),
            "liquidity_filter": str(payload.get("liquidity_filter") or "block LOW/THIN/WEAK option liquidity"),
            "expiry_behavior": str(payload.get("expiry_behavior") or "reduce confidence and prefer No Trade on elevated expiry risk"),
            "false_breakout_handling": str(payload.get("false_breakout_handling") or "require candle close confirmation before entry"),
        }

    # 3. Assign the pre-calculated float directly to the dictionary
        model["effective_slippage_per_side_bps"] = effective_slippage
        model["applied_to_results"] = True
        model["applied_components"] = ["brokerage", "brokerage_bps", "taxes", "slippage", "spread"]
        model["entry_delay_application"] = "recorded_as_latency_not_fill_shift"
        return model



def _backtest_period_years(candles: list[dict[str, Any]]) -> float:
        if len(candles) < 2:
            return 1 / 252
        start = _candle_timestamp(candles[0])
        end = _candle_timestamp(candles[-1])
        if start is None or end is None or end <= start:
            return max(len(candles) / (252 * 78), 1 / 252)
        days = max((end - start).total_seconds() / 86400, 1.0)
        return max(days / 365.0, 1 / 365)


def _candle_timestamp(candle: dict[str, Any]) -> datetime | None:
        raw = candle.get("timestamp")
        if raw is None:
            return None
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None


def risk_engine_summary() -> dict[str, Any]:
        risk = risk_status()
        halt = kill_switch_status()
        max_daily_loss = float(risk.get("max_daily_loss") or 0.0)
        daily_pnl = float(risk.get("daily_pnl") or 0.0)


        max_trades = int(
        risk.get("max_trades_per_day") or 0
        )
        checks = {
            "daily_loss": daily_pnl > -max_daily_loss if max_daily_loss else True,
            "max_trades": int(risk.get("trades_today") or 0) < max_trades,
            "open_positions":
                    int(risk.get("open_positions") or 0)
                    <
                    int(risk.get("max_open_positions") or 0),
            "consecutive_losses":
                    int(risk.get("consecutive_losses") or 0)
                    <
                    int(risk.get("max_consecutive_losses") or 0),
            "kill_switch":
                    not bool(halt.get("active")),
        }


        halted = not all(checks.values())
        return {
            "module": "risk_engine",
            "state": "halted" if halted else "normal",
            "halted": halted,
            "checks": checks,
            "limits": {
                "max_daily_loss": risk.get("max_daily_loss"),
                "max_trades_per_day": risk.get("max_trades_per_day"),
                "max_open_positions": risk.get("max_open_positions"),
                "max_quantity": risk.get("max_quantity"),
                "risk_per_trade_pct": risk.get("risk_per_trade_pct"),
            },
            "summary": risk,
            "kill_switch": halt,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


def trade_journal_summary(limit: int = 100) -> dict[str, Any]:
        trades = list_paper_trades(limit)
        closed = [trade for trade in trades if str(trade.get("status") or "").lower() in {"closed", "exited", "completed"}]
        pnl_values = [float(trade.get("pnl") or 0.0) for trade in closed]
        wins = [value for value in pnl_values if value > 0]
        losses = [value for value in pnl_values if value < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        expectancy = mean(pnl_values) if pnl_values else 0.0
        strategy_pnl: dict[str, float] = {}
        day_performance: dict[str, float] = {}
        monthly_performance: dict[str, float] = {}
        rr_values: list[float] = []
        for trade in closed:
            pnl = float(trade.get("pnl") or 0.0)
            strategy = str(trade.get("strategy") or trade.get("strategy_name") or "unknown")
            strategy_pnl[strategy] = strategy_pnl.get(strategy, 0.0) + pnl
            created_at = str(trade.get("created_at") or trade.get("timestamp") or "")
            day_key = created_at[:10] or "unknown"
            month_key = created_at[:7] or "unknown"
            day_performance[day_key] = day_performance.get(day_key, 0.0) + pnl
            monthly_performance[month_key] = monthly_performance.get(month_key, 0.0) + pnl
            rr = _trade_risk_reward(trade)
            if rr is not None:
                rr_values.append(rr)
        ranked_strategies = sorted(strategy_pnl.items(), key=lambda item: item[1], reverse=True)
        return {
            "module": "trade_journal",
            "total_trades": len(trades),
            "closed_trades": len(closed),
            "win_rate": round(len(wins) / len(closed), 4) if closed else 0.0,
            "pnl": round(sum(pnl_values), 2),
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else round(gross_profit, 2) if gross_profit else 0.0,
            "expectancy": round(expectancy, 2),
            "max_drawdown": round(_max_drawdown(pnl_values), 2),
            "avg_win": round(mean(wins), 2) if wins else 0.0,
            "avg_loss": round(mean(losses), 2) if losses else 0.0,
            "average_win": round(mean(wins), 2) if wins else 0.0,
            "average_loss": round(mean(losses), 2) if losses else 0.0,
            "average_rr": round(mean(rr_values), 2) if rr_values else 0.0,
            "best_strategy": ranked_strategies[0][0] if ranked_strategies else None,
            "worst_strategy": ranked_strategies[-1][0] if ranked_strategies else None,
            "day_wise_performance": {key: round(value, 2) for key, value in sorted(day_performance.items())},
            "monthly_performance": {key: round(value, 2) for key, value in sorted(monthly_performance.items())},
            "recent_trades": trades[: min(limit, 20)],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


def _max_drawdown(pnl_values: list[float]) -> float:
        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for pnl in pnl_values:
            equity += pnl
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, equity - peak)
        return abs(max_drawdown)


def _trade_risk_reward(trade: dict[str, Any]) -> float | None:
    entry_raw = trade.get("entry") or trade.get("entry_price")
    stop_raw = trade.get("stop_loss")
    target_raw = trade.get("target") or trade.get("target_price")

    if entry_raw is None or stop_raw is None or target_raw is None:
        return None

    try:
        entry = float(entry_raw)
        stop = float(stop_raw)
        target = float(target_raw)

    except (TypeError, ValueError):
        return None

    risk = abs(entry - stop)

    if risk <= 0:
        return None

    return abs(target - entry) / risk

def module_dashboard(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            backtesting = backtesting_module(payload)
        except ValueError as exc:
            backtesting = {
                "module": "backtesting",
                "source": "provider-data-unavailable",
                "available": False,
                "warning": str(exc),
                "metrics": {},
                "cost_model": _backtest_cost_model(payload or {}),
                "equity_curve": [],
                "recent_outcomes": [],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        return {
                    "option_chain": live_nse_option_chain(),
            "backtesting": backtesting,
            "risk_engine": risk_engine_summary(),
            "trade_journal": trade_journal_summary(),
        }