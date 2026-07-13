from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
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


logger = logging.getLogger("quantgrid.option_chain")


def _norm_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _norm_pdf(value: float) -> float:
    return exp(-0.5 * value * value) / sqrt(2.0 * 3.141592653589793)


def _black_scholes_greeks(
    *,
    option_type: str,
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    rate: float,
) -> dict[str, float]:
    sigma_sqrt_t = max(volatility * sqrt(max(time_to_expiry, 1e-6)), 1e-9)
    d1 = (log(max(spot, 1e-9) / max(strike, 1e-9)) + (rate + 0.5 * volatility * volatility) * time_to_expiry) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t
    side = option_type.lower()
    delta = _norm_cdf(d1) if side == "call" else _norm_cdf(d1) - 1.0
    gamma = _norm_pdf(d1) / max(spot * sigma_sqrt_t, 1e-9)
    theta_call = (-(spot * _norm_pdf(d1) * volatility) / (2 * sqrt(max(time_to_expiry, 1e-6))) - rate * strike * exp(-rate * time_to_expiry) * _norm_cdf(d2)) / 365
    theta_put = (-(spot * _norm_pdf(d1) * volatility) / (2 * sqrt(max(time_to_expiry, 1e-6))) + rate * strike * exp(-rate * time_to_expiry) * _norm_cdf(-d2)) / 365
    vega = spot * _norm_pdf(d1) * sqrt(max(time_to_expiry, 1e-6)) / 100
    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta_call if side == "call" else theta_put, 4),
        "vega": round(vega, 4),
    }


def _round_to_step(value: float, step: int) -> int:
    return int(round(value / step) * step)


def _latest_underlying_price(symbol: str, fallback: float = 22500.0) -> float:
    tick = latest_price_tick(symbol)
    if tick and tick.get("price"):
        return float(tick["price"])
    candles = latest_candles(symbol, "1m", 1) or latest_candles(symbol, "5m", 1)
    if candles:
        return float(candles[-1].get("close") or fallback)
    return fallback


def _max_pain(rows: list[dict[str, Any]]) -> int | None:
    if not rows:
        return None
    return min(
        rows,
        key=lambda candidate: sum(
            max(float(row["strike"]) - float(candidate["strike"]), 0.0) * float(row["ce"].get("oi") or 0)
            + max(float(candidate["strike"]) - float(row["strike"]), 0.0) * float(row["pe"].get("oi") or 0)
            for row in rows
        ),
    )["strike"]


def _nse_index_symbol(symbol: str) -> str:
    normalized = symbol.upper().strip()
    aliases = {
        "NIFTY": "NIFTY",
        "NIFTY50": "NIFTY",
        "BANKNIFTY": "BANKNIFTY",
        "FINNIFTY": "FINNIFTY",
        "MIDCPNIFTY": "MIDCPNIFTY",
    }
    return aliases.get(normalized, normalized)


def _nse_number(value: Any) -> float | int | None:
    if value in {None, ""}:
        return None
    number = float(value)
    return int(number) if number.is_integer() else round(number, 4)


def live_nse_option_chain(symbol: str = "NIFTY", *, strikes_each_side: int = 8, step: int = 50) -> dict[str, Any]:
    nse_symbol = _nse_index_symbol(symbol)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://www.nseindia.com/option-chain?symbol={quote(nse_symbol)}",
    }
    opener = build_opener(HTTPCookieProcessor())
    try:
        opener.open(Request("https://www.nseindia.com", headers=headers), timeout=8).read()
        response = opener.open(
            Request(f"https://www.nseindia.com/api/option-chain-indices?symbol={quote(nse_symbol)}", headers=headers),
            timeout=8,
        )
        payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.exception("live_nse_option_chain_fetch_failed", extra={"symbol": nse_symbol, "error_type": exc.__class__.__name__})
        observe_option_chain_failure("nse", exc.__class__.__name__)
        fallback = option_chain_engine(symbol, strikes_each_side=strikes_each_side, step=step)
        return _live_nse_fallback_payload(fallback, exc)
    records = payload.get("records") or {}
    raw_rows = records.get("data") or []
    expiry = next((item for item in records.get("expiryDates") or [] if item), None)
    underlying = float(records.get("underlyingValue") or _latest_underlying_price(symbol))
    atm = _round_to_step(underlying, step)
    lower = atm - strikes_each_side * step
    upper = atm + strikes_each_side * step
    rows: list[dict[str, Any]] = []

    for item in raw_rows:
        if expiry and item.get("expiryDate") != expiry:
            continue
        strike = int(round(float(item.get("strikePrice") or 0)))
        if strike < lower or strike > upper:
            continue
        ce = item.get("CE") or {}
        pe = item.get("PE") or {}
        rows.append(
            {
                "strike": strike,
                "ce": {
                    "ltp": _nse_number(ce.get("lastPrice")),
                    "change": _nse_number(ce.get("change")),
                    "volume": _nse_number(ce.get("totalTradedVolume")),
                    "oi": _nse_number(ce.get("openInterest")),
                    "iv": _nse_number(ce.get("impliedVolatility")),
                    "greeks": None,
                },
                "pe": {
                    "ltp": _nse_number(pe.get("lastPrice")),
                    "change": _nse_number(pe.get("change")),
                    "volume": _nse_number(pe.get("totalTradedVolume")),
                    "oi": _nse_number(pe.get("openInterest")),
                    "iv": _nse_number(pe.get("impliedVolatility")),
                    "greeks": None,
                },
            }
        )

    rows = sorted(rows, key=lambda row: row["strike"])
    if not rows:
        exc = RuntimeError("NSE returned no option-chain rows for the selected strike range.")
        logger.error("live_nse_option_chain_empty", extra={"symbol": nse_symbol, "error_type": exc.__class__.__name__})
        observe_option_chain_failure("nse", exc.__class__.__name__)
        return _live_nse_fallback_payload(option_chain_engine(symbol, strikes_each_side=strikes_each_side, step=step), exc)

    total_call_oi = sum(float(row["ce"].get("oi") or 0) for row in rows)
    total_put_oi = sum(float(row["pe"].get("oi") or 0) for row in rows)
    for row in rows:
        strike = float(row["strike"])
        iv = float(row["ce"].get("iv") or row["pe"].get("iv") or 18.0) / 100
        row["ce"]["greeks"] = _black_scholes_greeks(
            option_type="call",
            spot=underlying,
            strike=strike,
            time_to_expiry=7 / 365,
            volatility=max(iv, 0.01),
            rate=0.06,
        )
        row["pe"]["greeks"] = _black_scholes_greeks(
            option_type="put",
            spot=underlying,
            strike=strike,
            time_to_expiry=7 / 365,
            volatility=max(iv, 0.01),
            rate=0.06,
        )

    max_pain = _max_pain(rows)
    pcr = round(total_put_oi / total_call_oi, 3) if total_call_oi else 0.0
    signal_bias = "NEUTRAL"
    signal_reason = "PCR and max pain are balanced around ATM."
    if pcr >= 1.15 and max_pain and max_pain >= atm:
        signal_bias = "BULLISH"
        signal_reason = "Put OI is dominant and max pain is at or above ATM."
    elif pcr <= 0.85 and max_pain and max_pain <= atm:
        signal_bias = "BEARISH"
        signal_reason = "Call OI is dominant and max pain is at or below ATM."
    elif pcr >= 1.15:
        signal_bias = "PUT_SUPPORT"
        signal_reason = "Put-call ratio shows stronger put-side open interest."
    elif pcr <= 0.85:
        signal_bias = "CALL_RESISTANCE"
        signal_reason = "Put-call ratio shows stronger call-side open interest."

    return _option_chain_compat_payload({
        "module": "live_nse_option_chain",
        "symbol": nse_symbol,
        "underlying_price": round(underlying, 2),
        "atm_strike": atm,
        "expiry": expiry,
        "step": step,
        "source": "live-nse-chain",
        "pcr": pcr,
        "max_pain": max_pain,
        "greek_model": "black_scholes_from_nse_iv",
        "signals": {
            "bias": signal_bias,
            "reason": signal_reason,
            "total_call_oi": int(total_call_oi),
            "total_put_oi": int(total_put_oi),
            "pcr": pcr,
            "atm_strike": atm,
            "max_pain": max_pain,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    })


def _live_nse_fallback_payload(payload: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return _option_chain_compat_payload({
        **payload,
        "module": "live_nse_option_chain",
        "source": "synthetic-demo-chain",
        "synthetic": True,
        "fallback_reason": exc.__class__.__name__,
        "provider_warning": "Live NSE option-chain provider unavailable; using synthetic fallback data.",
        "fallback_detail": str(exc),
        "signals": {
            "bias": "NEUTRAL",
            "reason": "Live NSE option-chain is unavailable; synthetic fallback is for display only.",
            "total_call_oi": int(sum(float(row["ce"].get("oi") or 0) for row in payload["rows"])),
            "total_put_oi": int(sum(float(row["pe"].get("oi") or 0) for row in payload["rows"])),
            "pcr": payload.get("pcr"),
            "atm_strike": payload.get("atm_strike"),
            "max_pain": payload.get("max_pain"),
        },
    })


def _option_chain_compat_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rows = list(payload.get("rows") or [])
    atm = payload.get("atm_strike")
    support = None
    resistance = None
    below = [row for row in rows if atm is not None and float(row.get("strike") or 0) < float(atm)]
    above = [row for row in rows if atm is not None and float(row.get("strike") or 0) > float(atm)]
    if below:
        support = max(below, key=lambda row: float(row.get("pe", {}).get("oi") or 0)).get("strike")
    if above:
        resistance = max(above, key=lambda row: float(row.get("ce", {}).get("oi") or 0)).get("strike")
    pcr = float(payload.get("pcr") or 0.0)
    max_pain = payload.get("max_pain")
    spot = float(payload.get("underlying_price") or payload.get("spot") or 0.0)
    if pcr >= 1.15 and max_pain and spot >= float(max_pain):
        signal = "BUY_CE"
    elif pcr <= 0.85 and max_pain and spot <= float(max_pain):
        signal = "BUY_PE"
    else:
        signal = "NO_TRADE"
    raw_source = str(payload.get("source") or "")
    source = "live" if raw_source in {"live", "live-nse-chain"} else raw_source or "synthetic-demo-chain"
    return {
        **payload,
        "underlying": payload.get("symbol") or payload.get("underlying") or "NIFTY",
        "spot": spot,
        "ATM": atm,
        "atm": atm,
        "PCR": pcr,
        "pcr": pcr,
        "support": support if support is not None else payload.get("max_pain"),
        "resistance": resistance if resistance is not None else payload.get("max_pain"),
        "source": source,
        "legacy_source": raw_source,
        "signal": signal,
    }


def option_chain_engine(symbol: str = "NIFTY", *, strikes_each_side: int = 5, step: int = 50) -> dict[str, Any]:
    step = max(1, int(step))
    strikes_each_side = max(1, min(int(strikes_each_side), 12))
    spot = _latest_underlying_price(symbol)
    atm = _round_to_step(spot, step)
    expiry_date = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
    time_to_expiry = 7 / 365
    volatility = 0.18
    rate = 0.06
    rows: list[dict[str, Any]] = []

    for offset in range(-strikes_each_side, strikes_each_side + 1):
        strike = atm + offset * step
        distance = abs(strike - spot)
        intrinsic_call = max(spot - strike, 0.0)
        intrinsic_put = max(strike - spot, 0.0)
        time_value = max(12.0, 95.0 * exp(-distance / max(step * 4, 1)))
        call_oi = int(90000 + max(offset, 0) * 17500 + distance * 80)
        put_oi = int(90000 + max(-offset, 0) * 17500 + distance * 80)
        rows.append(
            {
                "strike": strike,
                "ce": {
                    "ltp": round(intrinsic_call + time_value, 2),
                    "oi": call_oi,
                    "volume": int(call_oi * 0.18),
                    "iv": volatility,
                    "greeks": _black_scholes_greeks(
                        option_type="call",
                        spot=spot,
                        strike=strike,
                        time_to_expiry=time_to_expiry,
                        volatility=volatility,
                        rate=rate,
                    ),
                },
                "pe": {
                    "ltp": round(intrinsic_put + time_value, 2),
                    "oi": put_oi,
                    "volume": int(put_oi * 0.18),
                    "iv": volatility,
                    "greeks": _black_scholes_greeks(
                        option_type="put",
                        spot=spot,
                        strike=strike,
                        time_to_expiry=time_to_expiry,
                        volatility=volatility,
                        rate=rate,
                    ),
                },
            }
        )

    total_call_oi = sum(float(row["ce"]["oi"] or 0) for row in rows)
    total_put_oi = sum(float(row["pe"]["oi"] or 0) for row in rows)
    return _option_chain_compat_payload({
        "module": "option_chain_engine",
        "symbol": symbol.upper(),
        "underlying_price": round(spot, 2),
        "atm_strike": atm,
        "expiry": expiry_date,
        "step": step,
        "source": "synthetic-demo-chain",
        "synthetic": True,
        "pcr": round(total_put_oi / total_call_oi, 3) if total_call_oi else 0.0,
        "max_pain": _max_pain(rows),
        "greek_model": "black_scholes_demo",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    })


def historical_option_chain(symbol: str = "NIFTY", *, periods: int = 12, step: int = 50) -> dict[str, Any]:
    periods = max(1, min(int(periods), 48))
    base_price = _latest_underlying_price(symbol)
    now = datetime.now(timezone.utc)
    snapshots: list[dict[str, Any]] = []

    for index in range(periods):
        age = periods - index - 1
        synthetic_price = base_price + ((index % 5) - 2) * 18 - age * 1.75
        atm = _round_to_step(synthetic_price, step)
        call_oi = 950000 + index * 7200 + max(synthetic_price - atm, 0) * 120
        put_oi = 940000 + (periods - index) * 6500 + max(atm - synthetic_price, 0) * 120
        pcr = put_oi / call_oi if call_oi else 0.0
        snapshots.append(
            {
                "timestamp": (now - timedelta(minutes=5 * age)).isoformat(),
                "underlying_price": round(synthetic_price, 2),
                "atm_strike": atm,
                "pcr": round(pcr, 3),
                "max_pain": atm + (step if pcr > 1.05 else -step if pcr < 0.95 else 0),
                "call_oi": int(call_oi),
                "put_oi": int(put_oi),
            }
        )

    return {
        "module": "historical_option_chain",
        "symbol": symbol.upper(),
        "source": "synthetic-historical-chain",
        "interval": "5m",
        "snapshots": snapshots,
        "updated_at": now.isoformat(),
    }


def _sample_candles(symbol: str) -> list[dict[str, Any]]:
    candles = latest_candles(symbol, "5m", 160)
    if candles:
        return candles
    base = _latest_underlying_price(symbol)
    now = datetime.now(timezone.utc) - timedelta(minutes=5 * 80)
    generated = []
    for index in range(80):
        close = base + ((index % 9) - 4) * 12 + index * 1.5
        generated.append(
            {
                "timestamp": (now + timedelta(minutes=5 * index)).isoformat(),
                "open": close - 8,
                "high": close + 18,
                "low": close - 18,
                "close": close,
                "volume": 1000 + index * 10,
            }
        )
    return generated


def backtesting_module(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    symbol = str(payload.get("symbol") or "NIFTY").upper()
    capital = float(payload.get("capital") or 100000)
    candles = payload.get("candles") or _sample_candles(symbol)
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
        latency_ms=cost_model["entry_delay_seconds"] * 1000,
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


def _backtest_cost_model(payload: dict[str, Any]) -> dict[str, Any]:
    model = {
        "brokerage_per_order": float(payload.get("brokerage_per_order", 20.0)),
        "brokerage_bps": float(payload.get("brokerage_bps", 0.0)),
        "taxes_bps": float(payload.get("taxes_bps", 2.5)),
        "slippage_bps": float(payload.get("slippage_bps", 5.0)),
        "spread_bps": float(payload.get("spread_bps", 8.0)),
        "entry_delay_seconds": int(payload.get("entry_delay_seconds", 60)),
        "candle_confirmation": bool(payload.get("candle_confirmation", True)),
        "gap_opening_policy": str(payload.get("gap_opening_policy") or "skip first candle after large gap"),
        "liquidity_filter": str(payload.get("liquidity_filter") or "block LOW/THIN/WEAK option liquidity"),
        "expiry_behavior": str(payload.get("expiry_behavior") or "reduce confidence and prefer No Trade on elevated expiry risk"),
        "false_breakout_handling": str(payload.get("false_breakout_handling") or "require candle close confirmation before entry"),
    }
    model["effective_slippage_per_side_bps"] = model["slippage_bps"] + model["spread_bps"] / 2.0
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
    checks = {
        "daily_loss": daily_pnl > -max_daily_loss if max_daily_loss else True,
        "trades_per_day": int(risk.get("trades_today") or 0) < int(risk.get("max_trades_per_day") or 0),
        "open_positions": int(risk.get("open_positions") or 0) < int(risk.get("max_open_positions") or 0),
        "consecutive_losses": int(risk.get("consecutive_losses") or 0) < int(risk.get("max_consecutive_losses") or 0),
        "kill_switch": not bool(halt.get("active")),
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
    try:
        entry = float(trade.get("entry") or trade.get("entry_price"))
        stop = float(trade.get("stop_loss"))
        target = float(trade.get("target") or trade.get("target_price"))
    except (TypeError, ValueError):
        return None
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    return abs(target - entry) / risk


def module_dashboard(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "option_chain": option_chain_engine(),
        "backtesting": backtesting_module(payload),
        "risk_engine": risk_engine_summary(),
        "trade_journal": trade_journal_summary(),
    }


