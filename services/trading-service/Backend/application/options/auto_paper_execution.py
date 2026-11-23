"""Long-only NIFTY CE/PE paper fills using contract premiums and master lots."""
from __future__ import annotations

import hashlib
import logging
import math
import os
from datetime import datetime, time, timezone

from Backend.application.candle_validation import get_market_session
from Backend.application.kill_switch import kill_switch_status
from Backend.application.options.option_buyer_limits import OptionBuyerLimits
from Backend.application.options.quote_freshness import verify_exchange_quote_timestamp
from Backend.application.options.paper_order_ledger import (
    IdempotencyConflict, close_option_position, ledger_path, list_option_positions,
    mark_option_position, record_verified_paper_buy,
)
from Backend.application.paper_trade_store import risk_status
from Backend.infrastructure.market_data.dhan_option_execution import IST, contract_quotes, select_contract

logger = logging.getLogger(__name__)
SQUARE_OFF_TIME = time(15, 20)


def _number(value, name):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_{name}") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"invalid_{name}")
    return result


def execute_option_paper(signal, *, capital: float, risk_pct: float, rr_ratio: float) -> dict:
    """Resolve the underlying direction, then size and fill the option at ask."""
    if signal.symbol.upper() != "NIFTY" or signal.side.upper() not in {"BUY", "SELL"}:
        return {"status": "no_trade", "reason": "unsupported_option_signal"}
    if signal.signal_time.tzinfo is None:
        return {"status": "no_trade", "reason": "signal_timestamp_without_timezone"}
    side = "CE" if signal.side.upper() == "BUY" else "PE"
    identity = f"{signal.strategy_name}|NIFTY|{signal.signal_time.astimezone(timezone.utc).isoformat()}|{side}"
    key = hashlib.sha256(identity.encode()).hexdigest()
    path = ledger_path()
    existing = next((row for row in list_option_positions(path) if row["actor_id"] == "auto-paper" and row["idempotency_key"] == key), None)
    if existing:
        return _result(existing, replayed=True)
    if not get_market_session().market_live or datetime.now(IST).time() >= SQUARE_OFF_TIME:
        return {"status": "no_trade", "reason": "outside_option_entry_hours"}
    switch = kill_switch_status(fresh=True)
    if switch.get("active") is not False:
        return {"status": "no_trade", "reason": "KILL_SWITCH_ACTIVE"}
    try:
        contract = select_contract(_number(signal.entry_price, "underlying_price"), side)
        quote = contract_quotes([contract["security_id"]])[contract["security_id"]]
        ask, bid, lot = quote["ask"], quote["bid"], contract["lot_size"]
        if (ask - bid) / ask > 0.03:
            return {"status": "no_trade", "reason": "option_spread_too_wide"}
        account = risk_status(include_closed_outcomes=True)
        risk_budget = min(_number(account["risk_per_trade_amount"], "account_risk"),
                          _number(capital, "capital") * _number(risk_pct, "risk_pct") / 100)
        stop_pct = _number(os.getenv("QUANTGRID_OPTION_PAPER_STOP_LOSS_PCT", "20"), "option_stop_pct")
        if stop_pct >= 100:
            raise ValueError("invalid_option_stop_pct")
        stop = round(ask * (1 - stop_pct / 100), 2)
        target = round(ask + (ask - stop) * _number(rr_ratio, "rr_ratio"), 2)
        if not 0 < stop < ask < target:
            raise ValueError("invalid_option_exit_levels")
        premium_limit = min(OptionBuyerLimits().paper_max_premium_rupees,
                            _number(os.getenv("QUANTGRID_MAX_ORDER_NOTIONAL", "1000000"), "premium_limit"),
                            _number(account["capital"], "account_capital"))
        lots = min(10, math.floor(risk_budget / ((ask - stop) * lot)),
                   math.floor(premium_limit / (ask * lot)), int(account["max_quantity"]) // lot,
                   quote["ask_quantity"] // lot)
        if lots < 1:
            return {"status": "no_trade", "reason": "option_lot_exceeds_budget_or_depth",
                    "option_type": side, "premium": ask, "lot_size": lot,
                    "one_lot_premium": round(ask * lot, 2), "risk_budget": risk_budget}
        # Re-read safety state immediately before the atomic paper transaction.
        if kill_switch_status(fresh=True).get("active") is not False:
            return {"status": "no_trade", "reason": "KILL_SWITCH_ACTIVE"}
        verify_exchange_quote_timestamp(quote["quote_timestamp"], now=datetime.now(timezone.utc))
        if not get_market_session().market_live or datetime.now(IST).time() >= SQUARE_OFF_TIME:
            return {"status": "no_trade", "reason": "outside_option_entry_hours"}
        verified = {**contract, **quote, "side": side, "lots": lots,
                    "execution_mode": "paper", "eligible": True,
                    "stop_loss": stop, "target": target, "strategy": signal.strategy_name,
                    "signal_time": signal.signal_time.isoformat()}
        try:
            saved = record_verified_paper_buy(path, "auto-paper", key, verified,
                                              max_open_premium_rupees=premium_limit, limits=account)
        except IdempotencyConflict:
            # A competing scanner may have committed the same signal with an
            # earlier ask. Return its durable fill instead of placing another.
            existing = next(row for row in list_option_positions(path)
                            if row["actor_id"] == "auto-paper" and row["idempotency_key"] == key)
            return _result(existing, replayed=True)
        row = next(row for row in list_option_positions(path) if row["id"] == saved["order_id"])
        return _result(row, replayed=saved["replayed"])
    except (ValueError, RuntimeError, OSError) as exc:
        logger.warning("option_paper_no_trade reason=%s", str(exc))
        return {"status": "no_trade", "reason": str(exc)}


def _result(row, *, replayed):
    return {"status": "paper_simulated", "source": "auto_option_signal",
            "paper_trade_id": row["id"], "option_order_id": row["id"], "replayed": replayed,
            "execution_mode": "paper", "broker_submitted": False,
            "order": {"symbol": row["symbol"], "side": "BUY", "quantity": row["quantity"],
                      "price": row["entry_price"], "stop_loss": row.get("stop_loss"),
                      "target_price": row.get("target"), "security_id": row["security_id"],
                      "option_type": row["option_type"], "expiry": row["expiry"],
                      "strike": row["strike"], "lot_size": row["lot_size"]}}


def exit_option_paper(order_id: int, reason: str = "manual_exit") -> dict:
    path = ledger_path()
    row = next((item for item in list_option_positions(path) if item["id"] == order_id), None)
    if row is None:
        raise ValueError("option paper position not found")
    if row["status"] == "closed":
        return row
    quote = contract_quotes([row["security_id"]])[row["security_id"]]
    if quote["bid_quantity"] < row["quantity"]:
        raise ValueError("insufficient_option_exit_depth")
    return close_option_position(path, order_id, quote["bid"], reason)


def monitor_option_positions() -> dict:
    """Mark and close long paper positions using fresh option bids."""
    positions = [row for row in list_option_positions() if row["status"] == "open"]
    if not positions or not get_market_session().market_live:
        return {"closed": [], "open": len(positions)}
    closed = []
    for row in positions:
        try:
            quote = contract_quotes([row["security_id"]])[row["security_id"]]
            mark_option_position(ledger_path(), row["id"], quote["bid"], quote["quote_timestamp"])
            reason = None
            if row.get("stop_loss") and quote["bid"] <= row["stop_loss"]:
                reason = "stop_loss_hit"
            elif row.get("target") and quote["bid"] >= row["target"]:
                reason = "target_hit"
            elif datetime.now(IST).time() >= SQUARE_OFF_TIME:
                reason = "session_square_off"
            if reason and quote["bid_quantity"] >= row["quantity"]:
                closed.append(close_option_position(ledger_path(), row["id"], quote["bid"], reason))
        except Exception:
            logger.exception("Option paper monitor failed order_id=%s", row["id"])
    return {"closed": closed, "open": len(positions) - len(closed)}
