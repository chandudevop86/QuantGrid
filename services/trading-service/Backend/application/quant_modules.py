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
    dividend: float = 0.0
    ) -> dict[str, float]:
    spot = max(spot, 1e-9)
    strike = max(strike, 1e-9)

    sigma_sqrt_t = max(volatility * sqrt(max(time_to_expiry, 1e-6)), 1e-9)

    d1 = (
        log(spot / strike)
        + (rate - dividend + 0.5 * volatility ** 2)
        * time_to_expiry
        ) / sigma_sqrt_t
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



def _max_pain(rows: list[dict[str, Any]]) -> int | None:
    if not rows:
        return None

    def pain(candidate: dict[str, Any]) -> float:
        candidate_strike = float(candidate.get("strike") or 0)

        return sum(
            max(float(row.get("strike") or 0) - candidate_strike, 0.0)
            * float((row.get("ce") or {}).get("oi") or 0)
            +
            max(candidate_strike - float(row.get("strike") or 0), 0.0)
            * float((row.get("pe") or {}).get("oi") or 0)
            for row in rows
        )

    result = min(rows, key=pain)
    strike = result.get("strike")

    if isinstance(strike, (int, float)):
        return int(strike)

    if isinstance(strike, str):
        try:
                return int(float(strike))
        except ValueError:
                return None

    return None

def _professional_option_signal(
    rows: list[dict[str, Any]],
        *,
        spot: float,
        atm: int,
        pcr: float | None,
        max_pain: int | None,

        ) -> dict[str, Any]:
        """
        Production option-chain signal engine.

        Returns
        -------
        {
            signal,
            confidence,
            bias,
            reasons,
            support,
            resistance
        }
        """

        if not rows:
            return {
                "signal": "NO_TRADE",
                "bias": "NEUTRAL",
                "confidence": 0,
                "support": None,
                "resistance": None,
                "reasons": ["Empty option chain"],
            }

        below = [r for r in rows if r["strike"] <= atm]
        above = [r for r in rows if r["strike"] >= atm]

        support = None
        resistance = None

        if below:
            support = max(
                below,
                key=lambda x: float(x["pe"].get("oi") or 0)
            )["strike"]

        if above:
            resistance = max(
                above,
                key=lambda x: float(x["ce"].get("oi") or 0)
            )["strike"]

        score = 0
        reasons = []

##########################################
#             PCR
##########################################

        if pcr is not None:

            if pcr >= 1.30:
                score += 30
                reasons.append("Bullish PCR")

            elif pcr >= 1.10:
                score += 15
                reasons.append("Positive PCR")

            elif pcr <= 0.70:
                score -= 30
                reasons.append("Bearish PCR")

            elif pcr <= 0.90:
                score -= 15
                reasons.append("Weak PCR")

##########################################
            # Max Pain
##########################################

        if max_pain is not None:

            distance = abs(spot - max_pain)

            if distance <= 50:
                reasons.append("Near Max Pain")

            if spot > max_pain:
                score += 10
                reasons.append("Above Max Pain")

            elif spot < max_pain:
                score -= 10
                reasons.append("Below Max Pain")
                
            
##########################################
# Support
##########################################

        if support:

                if spot > support:
                    score += 15
                    reasons.append("Above Support")

                else:
                    score -= 20
                    reasons.append("Support Broken")

##########################################
# Resistance
##########################################

        if resistance:

            if spot < resistance:
                score += 5

            else:
                score -= 20
                reasons.append("Resistance Breakout Failure")

##########################################
# ATM Greeks
##########################################

        atm_row = next(
            (
                r
                for r in rows
                if r["strike"] == atm
            ),
            None,
        )

        if atm_row:

            call_delta = float(
                atm_row["ce"]["greeks"]["delta"]
            )

            put_delta = abs(
                float(
                    atm_row["pe"]["greeks"]["delta"]
                )
            )

            gamma = float(
                atm_row["ce"]["greeks"]["gamma"]
            )

            iv = float(
                atm_row["ce"].get("iv") or 20
            )

            ##################################

            if gamma > 0.0008:
                score += 5
                reasons.append("High Gamma")

            ##################################

            if iv < 15:
                score += 5
                reasons.append("Low IV")

            elif iv > 30:
                score -= 5
                reasons.append("High IV")

            ##################################

            if call_delta > put_delta:
                score += 5

            else:
                score -= 5

        ##########################################
        # Confidence
        ##########################################
        MAX_SCORE = 70
        confidence = min(
            round(abs(score) / MAX_SCORE * 100),
        100,
        )

        ##########################################
        # Final Signal
        ##########################################

        if score >= 40:

            signal = "BUY_CE"
            bias = "BULLISH"

        elif score <= -40:

            signal = "BUY_PE"
            bias = "BEARISH"

        else:

            signal = "NO_TRADE"
            bias = "NEUTRAL"

        ##########################################

        return {

            "signal": signal,
            
            "bias": bias,

            "confidence": confidence,

            "score": score,

            "support": support,

            "resistance": resistance,
            
            "max_pain": max_pain,
            "reasons": reasons,
        }

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

def _time_to_expiry(expiry: str | None) -> float:
        if not expiry:
            return 1 / 365

        try:
            expiry_dt = datetime.strptime(
                expiry,
                "%d-%b-%Y"
            ).replace(
                tzinfo=timezone.utc
            )

            seconds = (
                expiry_dt -
                datetime.now(timezone.utc)
            ).total_seconds()

            return max(seconds / (365 * 24 * 3600), 0.001)

        except Exception:
            return 1 / 365

def _nse_number(value: Any) -> float | int | None:
            if value in {None, ""}:
                return None
            try:
                number = float(value)
            except (TypeError, ValueError):
                return None

            return int(number) if number.is_integer() else round(number, 4)


def live_nse_option_chain(
    symbol: str = "NIFTY",
    *,
    strikes_each_side: int = 8,
    step: int = 50,
    ) -> dict[str, Any]:

    nse_symbol = _nse_index_symbol(symbol)

    try:
        payload = fetch_nse_option_chain(nse_symbol)

    except Exception as exc:
        logger.exception("live_nse_option_chain_fetch_failed")

        observe_option_chain_failure(
            "nse",
            exc.__class__.__name__,
        )

        return _live_nse_fallback_payload(
            option_chain_engine(
                symbol,
                strikes_each_side=strikes_each_side,
                step=step,
        ),
        exc,
    )

    records = payload.get("records") or {}
    raw_rows = records.get("data") or []
    expiry = next( (x for x in records.get("expiryDates") or [] if x),None,)
    underlying = float(records.get("underlyingValue") or _latest_underlying_price(symbol))
    tte = _time_to_expiry(expiry)
    expiry_days = round(tte * 365, 2)
    atm = _round_to_step(underlying,step,)
    lower = atm - strikes_each_side * step
    upper = atm + strikes_each_side * step

    rows = []

    for item in raw_rows:

        if expiry and item.get("expiryDate") != expiry:
            continue

        strike = int(item["strikePrice"])

        strike = int(item["strikePrice"])

        if strike < lower or strike > upper:
                continue

        ce = item.get("CE") or {}
        pe = item.get("PE") or {}
        ce_iv = max(float(ce.get("impliedVolatility") or 20) / 100, 0.01)
        pe_iv = max(float(pe.get("impliedVolatility") or 20) / 100, 0.01)
        rows.append(
                {
                "strike": strike,
                "ce": {
                    "ltp": _nse_number(ce.get("lastPrice")),
                    "change": _nse_number(ce.get("change")),
                    "volume": _nse_number(ce.get("totalTradedVolume")),
                    "oi": _nse_number(ce.get("openInterest")),
                    "iv": _nse_number(ce.get("impliedVolatility")),
                    "oi_change": _nse_number(ce.get("changeinOpenInterest")),
                    "greeks": _black_scholes_greeks(
                        option_type="call",
                        spot=underlying,
                        strike=strike,
                        time_to_expiry=tte,
                        volatility=ce_iv,
                        rate=0.06,
                    ),
                },
                "pe": {
                    "ltp": _nse_number(pe.get("lastPrice")),
                    "change": _nse_number(pe.get("change")),
                    "volume": _nse_number(pe.get("totalTradedVolume")),
                    "oi": _nse_number(pe.get("openInterest")),
                    "iv": _nse_number(pe.get("impliedVolatility")),
                    "oi_change": _nse_number(pe.get("changeinOpenInterest")),
                    "greeks": _black_scholes_greeks(
                        option_type="put",
                        spot=underlying,
                        strike=strike,
                        time_to_expiry=tte,
                        volatility=pe_iv,
                        rate=0.06,
                    ),
                },
            }
        )

    rows = sorted(
                rows,
                key=lambda row: int(cast(Dict[str, Any], row).get("strike") or 0)

    )

    if not rows:
        empty_chain_error = RuntimeError(
            "NSE returned empty option chain"
        )

        observe_option_chain_failure(
            "nse",
            empty_chain_error.__class__.__name__,
        )

        return _live_nse_fallback_payload(
            option_chain_engine(
                symbol,
                strikes_each_side=strikes_each_side,
                step=step,
            ),
            empty_chain_error,
        )
    typed_rows = cast(List[Dict[str, Any]], rows)   
    total_call_oi = sum(
        float((r.get("ce") or {}).get("oi") or 0)
        for r in typed_rows)

    total_put_oi = sum(
        float((r.get("pe") or {}).get("oi") or 0)
        for r in typed_rows)

    total_call_oi_change = sum(
        float((r.get("ce") or {}).get("oi_change") or 0)
        for r in typed_rows)

    total_put_oi_change = sum(
        float((r.get("pe") or {}).get("oi_change") or 0)
        for r in typed_rows)

    pcr = (
        round(total_put_oi / total_call_oi, 3)
        if total_call_oi
        else None
    )

    max_pain = _max_pain(rows)
# -------------------------------------------------
#        Build professional signal
# -------------------------------------------------
    signal_data = _professional_option_signal(
        rows,
        spot=underlying,
        atm=atm,
        pcr=pcr,
        max_pain=max_pain,
    )
# -------------------------------------------------
#           SUCCESS PAYLOAD
# -------------------------------------------------
    return _option_chain_compat_payload(
                
        {
            "module": "live_nse_option_chain",
            "symbol": symbol.upper(),
            "underlying_price": underlying,
            "atm_strike": atm,
            "expiry": expiry,
            "step": step,
            "rows": rows,
            "pcr": pcr,
            "max_pain": max_pain,
            "total_call_oi": total_call_oi,
            "total_put_oi": total_put_oi,
            "total_call_oi_change": total_call_oi_change,
            "total_put_oi_change": total_put_oi_change,
            "source": "live-nse-chain",
            "provider_available": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "expiry_days": expiry_days,
            "signal": signal_data["signal"],
            "signals": signal_data,
    }
)

def _live_nse_fallback_payload(
    payload: dict[str, Any],
    exc: Exception,
    ) -> dict[str, Any]:

    return _option_chain_compat_payload(

            {
                "module": "live_nse_option_chain",
                "symbol": payload.get("symbol") or "NIFTY",
                "underlying_price": None,
                "atm_strike": None,
                "expiry": None,
                "step": payload.get("step") or 50,
                "source": "option-chain-unavailable",
                "synthetic": False,
                "provider_available": False,
                "fallback_reason": exc.__class__.__name__,
                "provider_warning": "Live NSE option-chain provider unavailable.",
                "fallback_detail": str(exc),
                "rows": [],
                "pcr": None,
                "max_pain": None,
                "signals": {
                    "signal": "NO_TRADE",
                    "bias": "NEUTRAL",
                    "confidence": 0,
                    "reason": "Live NSE option-chain unavailable.",
                    "support": None,
                    "resistance": None,
                    "max_pain": None,
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
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
def _option_chain_compat_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = [
        row
        for row in (payload.get("rows") or [])
        if isinstance(row, dict)
    ]

    atm = payload.get("atm_strike")

    support = None
    resistance = None

    below = [
        row
        for row in rows
        if atm is not None
        and float(row.get("strike") or 0) < float(atm)
    ]

    above = [
        row
        for row in rows
        if atm is not None
        and float(row.get("strike") or 0) > float(atm)
    ]

    if below:
        support = max(
            below,
            key=lambda row: float(
                (row.get("pe") or {}).get("oi") or 0
            ),
        ).get("strike")

    if above:
        resistance = max(
            above,
            key=lambda row: float(
                (row.get("ce") or {}).get("oi") or 0
            ),
        ).get("strike")

    raw_pcr = payload.get("pcr")
    pcr = float(raw_pcr) if raw_pcr is not None else None

    max_pain = payload.get("max_pain")

    raw_spot = (
        payload.get("underlying_price")
        if payload.get("underlying_price") is not None
        else payload.get("spot")
    )

    spot = float(raw_spot) if raw_spot is not None else None

    signal_data = payload.get("signals")

    if not isinstance(signal_data, dict):
        signal_data = {
            "signal": "NO_TRADE",
            "bias": "NEUTRAL",
            "confidence": 0,
            "score": 0,
            "support": support,
            "resistance": resistance,
            "max_pain": max_pain,
            "reasons": ["Signal engine not executed"],
        }

    raw_source = str(payload.get("source") or "")

    source = (
        "live"
        if raw_source in {"live", "live-nse-chain"}
        else raw_source or "option-chain-unavailable"
    )

    return {
        **payload,
        "underlying": (
            payload.get("symbol")
            or payload.get("underlying")
            or "NIFTY"
        ),
        "spot": spot,
        "ATM": atm,
        "atm": atm,
        "PCR": pcr,
        "pcr": pcr,
        "support": support if support is not None else max_pain,
        "resistance": resistance if resistance is not None else max_pain,
        "source": source,
        "legacy_source": raw_source,
        "signal": signal_data.get("signal", "NO_TRADE"),
        "signals": signal_data,
    }

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

