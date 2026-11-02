"""Research-only option and futures metrics; no investment or order signal."""
from datetime import datetime, timezone
import math


def analyze_derivatives(*, symbol, spot, future, call_oi, put_oi,
                        call_iv, put_iv, quote_timestamp, now=None):
    if not isinstance(symbol, str) or not symbol or len(symbol) > 32:
        return {"valid": False, "reason": "invalid symbol"}
    values = (spot, future, call_oi, put_oi, call_iv, put_iv)
    if any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in values):
        return {"valid": False, "reason": "invalid quote"}
    if spot <= 0 or call_oi <= 0:
        return {"valid": False, "reason": "missing spot or call open interest"}
    try:
        ts = datetime.fromisoformat(quote_timestamp.replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        if ts.tzinfo is None or not 0 <= (current - ts).total_seconds() <= 15:
            return {"valid": False, "reason": "stale quote"}
    except (TypeError, AttributeError, ValueError, OverflowError):
        return {"valid": False, "reason": "missing timestamp provenance"}
    basis = future - spot
    return {"valid": True, "symbol": symbol, "pcr": round(put_oi / call_oi, 4),
            "futures_basis": round(basis, 2),
            "futures_basis_pct": round(100 * basis / spot, 4),
            "put_call_iv_spread": round(put_iv - call_iv, 3),
            "recommendation": "none",
            "mode": "research_only",
            "limitations": ["OI and IV alone cannot predict direction",
                            "contract expiry, liquidity, fees and Greeks not yet evaluated"]}
