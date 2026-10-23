"""Fail-closed NIFTY option contract verification against a trusted instrument master.

The caller must supply rows from a separately authenticated, dated exchange
instrument master. Option-chain quote fields alone are never a master.
No broker orders are placed here.
"""
from datetime import date, datetime
from math import isfinite


class ContractMasterVerificationError(ValueError):
    pass


def verify_nifty_option_contract(*, master_row, security_id, expiry, strike, side,
                                 lot_size, as_of=None):
    """Return normalized contract identity or fail closed on any mismatch."""
    if not isinstance(master_row, dict):
        raise ContractMasterVerificationError("trusted contract master row required")
    if type(lot_size) is not int or lot_size <= 0:
        raise ContractMasterVerificationError("invalid exchange lot size")
    if side not in ("CE", "PE") or type(strike) not in (int, float) or not isfinite(strike) or strike <= 0:
        raise ContractMasterVerificationError("invalid option identity")
    try:
        master_security = str(master_row["security_id"])
        requested_security = str(security_id)
        master_expiry = date.fromisoformat(str(master_row["expiry"]))
        requested_expiry = date.fromisoformat(str(expiry))
        master_strike = float(master_row["strike"])
        master_lot = master_row["lot_size"]
        instrument = str(master_row["underlying"]).upper()
        master_side = str(master_row["side"]).upper()
        segment = str(master_row["segment"]).upper()
        today = as_of or datetime.now().date()
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise ContractMasterVerificationError("incomplete or invalid master record") from exc
    if (not master_security.isdecimal() or master_security != requested_security
            or instrument != "NIFTY" or segment != "NSE_FNO"
            or master_side != side or master_expiry != requested_expiry
            or master_expiry < today or not isfinite(master_strike)
            or master_strike != float(strike)
            or type(master_lot) is not int or master_lot != lot_size):
        raise ContractMasterVerificationError("option contract master mismatch")
    return {"symbol": "NIFTY", "security_id": master_security,
            "expiry": master_expiry.isoformat(), "strike": master_strike,
            "side": master_side, "lot_size": master_lot}
