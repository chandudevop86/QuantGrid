"""Long-only NIFTY CE/PE paper fills using contract premiums and master lots."""
from __future__ import annotations

import hashlib
import logging
import math
import os
from datetime import datetime, time, timezone
from types import SimpleNamespace

from Backend.application.candle_validation import get_market_session
from Backend.application.kill_switch import kill_switch_status
from Backend.application.options.option_buyer_limits import OptionBuyerLimits
from Backend.application.options.quote_freshness import verify_exchange_quote_timestamp
from Backend.application.options.paper_order_ledger import (
    IdempotencyConflict, close_option_position, ledger_path, list_option_positions,
    mark_option_position, record_verified_paper_buy, record_option_recovery, clear_option_recovery,
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
    return _execute_paper(signal, capital=capital, risk_pct=risk_pct, rr_ratio=rr_ratio)


def submit_manual_option_paper(*, actor_id: str, key: str, strike: int, side: str, lots: int) -> dict:
    if side not in {"CE", "PE"} or type(lots) is not int or not 1 <= lots <= 10:
        return {"status": "no_trade", "reason": "invalid_option_request"}
    account = risk_status(include_options=False)
    signal = SimpleNamespace(
        strategy_name="manual_option_buyer", symbol="NIFTY", side="BUY" if side == "CE" else "SELL",
        entry_price=strike, signal_time=datetime.now(timezone.utc), metadata={},
    )
    return _execute_paper(
        signal, capital=account["capital"], risk_pct=account["risk_per_trade_pct"], rr_ratio=2,
        actor_id=actor_id, request_key=key, requested_lots=lots, requested_strike=strike,
    )


def preview_option_paper(*, strike: int, side: str) -> dict:
    contract = select_contract(strike, side, strike=strike)
    quote = contract_quotes([contract["security_id"]])[contract["security_id"]]
    entry_hours = get_market_session().market_live and datetime.now(IST).time() < SQUARE_OFF_TIME
    switch = kill_switch_status(fresh=True)
    enabled = bool(entry_hours and switch.get("active") is False)
    return {**contract, "side": side, "quote": quote, "source": quote["quote_source"],
            "quote_timestamp": quote["quote_timestamp"], "quote_freshness_verified": True,
            "exchange_timestamp_provenance_verified": True, "exchange_lot_size_verified": True,
            "paper_order_enabled": enabled,
            "reason": "Verified paper contract. Order risk is checked again on submission." if enabled
            else "Paper entry requires an open market and inactive kill switch."}


def _execute_paper(signal, *, capital: float, risk_pct: float, rr_ratio: float,
                   actor_id="auto-paper", request_key=None, requested_lots=None, requested_strike=None) -> dict:
    """Resolve the underlying direction, then size and fill the option at ask."""
    if signal.symbol.upper() != "NIFTY" or signal.side.upper() not in {"BUY", "SELL"}:
        return {"status": "no_trade", "reason": "unsupported_option_signal"}
    if signal.signal_time.tzinfo is None:
        return {"status": "no_trade", "reason": "signal_timestamp_without_timezone"}
    side = "CE" if signal.side.upper() == "BUY" else "PE"
    identity = f"{signal.strategy_name}|NIFTY|{signal.signal_time.astimezone(timezone.utc).isoformat()}|{side}"
    key = request_key or hashlib.sha256(identity.encode()).hexdigest()
    path = ledger_path()
    existing = next((row for row in list_option_positions(path) if row["actor_id"] == actor_id and row["idempotency_key"] == key), None)
    if existing:
        if requested_lots is not None and (
            existing["option_type"] != side or existing["strike"] != requested_strike
            or existing["lots"] != requested_lots
        ):
            return {"status": "no_trade", "reason": "idempotency_key_conflict"}
        return _result(existing, replayed=True)
    if not get_market_session().market_live or datetime.now(IST).time() >= SQUARE_OFF_TIME:
        return {"status": "no_trade", "reason": "outside_option_entry_hours"}
    switch = kill_switch_status(fresh=True)
    if switch.get("active") is not False:
        return {"status": "no_trade", "reason": "KILL_SWITCH_ACTIVE"}
    try:
        spot = _number(signal.entry_price, "underlying_price")
        contract = (select_contract(spot, side) if requested_strike is None
                    else select_contract(spot, side, strike=requested_strike))
        quote = contract_quotes([contract["security_id"]])[contract["security_id"]]
        ask, bid, lot = quote["ask"], quote["bid"], contract["lot_size"]
        if (ask - bid) / ask > 0.03:
            return {"status": "no_trade", "reason": "option_spread_too_wide"}
        account = risk_status(include_options=False, include_closed_outcomes=True)
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
        affordable_lots = min(10, math.floor(risk_budget / ((ask - stop) * lot)),
                   math.floor(premium_limit / (ask * lot)), int(account["max_quantity"]) // lot,
                   quote["ask_quantity"] // lot)
        lots = affordable_lots if requested_lots is None else requested_lots
        if lots < 1 or lots > affordable_lots:
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
            saved = record_verified_paper_buy(path, actor_id, key, verified,
                                              max_open_premium_rupees=premium_limit, limits=account)
        except IdempotencyConflict:
            # A competing scanner may have committed the same signal with an
            # earlier ask. Return its durable fill instead of placing another.
            existing = next(row for row in list_option_positions(path)
                            if row["actor_id"] == actor_id and row["idempotency_key"] == key)
            if requested_lots is not None and (
                existing["option_type"] != side or existing["strike"] != requested_strike
                or existing["lots"] != requested_lots
            ):
                return {"status": "no_trade", "reason": "idempotency_key_conflict"}
            return _result(existing, replayed=True)
        row = next(row for row in list_option_positions(path) if row["id"] == saved["order_id"])
        return _result(row, replayed=saved["replayed"])
    except (ValueError, RuntimeError, OSError) as exc:
        logger.warning("option_paper_no_trade reason=%s", str(exc))
        return {"status": "no_trade", "reason": str(exc)}


def _result(row, *, replayed):
    source = "manual_option_buyer" if row.get("strategy") == "manual_option_buyer" else "auto_option_signal"
    return {"status": "paper_simulated", "source": source,
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
    if _contract_expired(row, datetime.now(IST)):
        record_option_recovery(path, order_id, "expired_contract_requires_verified_settlement")
        raise ValueError("expired_contract_requires_verified_settlement")
    quote = contract_quotes([row["security_id"]])[row["security_id"]]
    if quote["bid_quantity"] < row["quantity"]:
        raise ValueError("insufficient_option_exit_depth")
    return close_option_position(path, order_id, quote["bid"], reason)


def _contract_expired(row, now):
    expiry = datetime.fromisoformat(row["expiry"]).date()
    return expiry < now.date() or (expiry == now.date() and now.time() >= time(15, 30))


def settle_expired_option_paper(order_id: int, *, final_underlying_price: float,
                                evidence_reference: str, actor_id: str) -> dict:
    row = next((item for item in list_option_positions() if item["id"] == order_id), None)
    if row is None:
        raise ValueError("option paper position not found")
    if row["status"] == "closed":
        return row
    if not _contract_expired(row, datetime.now(IST)):
        raise ValueError("option_contract_not_expired")
    price = _number(final_underlying_price, "final_underlying_settlement")
    if not isinstance(evidence_reference, str) or not 8 <= len(evidence_reference.strip()) <= 500 or not actor_id:
        raise ValueError("reviewed_settlement_evidence_required")
    intrinsic = max(0.0, price - float(row["strike"]) if row["option_type"] == "CE"
                    else float(row["strike"]) - price)
    return close_option_position(
        ledger_path(), order_id, intrinsic, "expiry_settlement",
        settlement_evidence=evidence_reference.strip(), settlement_actor=actor_id,
    )


def monitor_option_positions() -> dict:
    """Mark and close long paper positions using fresh option bids."""
    positions = [row for row in list_option_positions() if row["status"] == "open"]
    market_live = get_market_session().market_live
    now = datetime.now(IST)
    closed = []
    errors = []
    for row in positions:
        try:
            if _contract_expired(row, now):
                reason = "expired_contract_requires_verified_settlement"
                record_option_recovery(ledger_path(), row["id"], reason)
                errors.append({"order_id": row["id"], "reason": reason})
                continue
            opened_day = datetime.fromisoformat(row["opened_at"]).astimezone(IST).date()
            overdue = opened_day < now.date() or now.time() >= SQUARE_OFF_TIME
            if not market_live:
                if overdue:
                    record_option_recovery(ledger_path(), row["id"], "overdue_square_off_pending")
                    errors.append({"order_id": row["id"], "reason": "overdue_square_off_pending"})
                continue
            quote = contract_quotes([row["security_id"]])[row["security_id"]]
            mark_option_position(ledger_path(), row["id"], quote["bid"], quote["quote_timestamp"])
            reason = None
            if overdue:
                reason = "overdue_square_off" if opened_day < now.date() else "session_square_off"
            elif row.get("stop_loss") and quote["bid"] <= row["stop_loss"]:
                reason = "stop_loss_hit"
            elif row.get("target") and quote["bid"] >= row["target"]:
                reason = "target_hit"
            if reason and quote["bid_quantity"] >= row["quantity"]:
                closed.append(close_option_position(ledger_path(), row["id"], quote["bid"], reason))
            elif reason:
                record_option_recovery(ledger_path(), row["id"], "insufficient_option_exit_depth")
                errors.append({"order_id": row["id"], "reason": "insufficient_option_exit_depth"})
            else:
                clear_option_recovery(ledger_path(), row["id"])
        except Exception:
            record_option_recovery(ledger_path(), row["id"], "option_exit_quote_unavailable")
            errors.append({"order_id": row["id"], "reason": "option_exit_quote_unavailable"})
            logger.exception("Option paper monitor failed order_id=%s", row["id"])
    return {"closed": closed, "open": len(positions) - len(closed), "errors": errors}
