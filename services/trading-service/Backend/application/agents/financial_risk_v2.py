"""Read-only financial risk diagnostics; never authorizes broker orders."""
import math


def evaluate_account_risk(*, cash, reserved_premium, open_option_premium,
                          futures_margin, unrealized_pnl, realized_pnl,
                          peak_equity, current_equity, daily_loss_limit=1000):
    numbers = (cash, reserved_premium, open_option_premium, futures_margin,
               unrealized_pnl, realized_pnl, peak_equity, current_equity, daily_loss_limit)
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in numbers):
        return {"valid": False, "trading_permitted": False, "reasons": ["invalid account data"]}
    if any(x < 0 for x in (cash, reserved_premium, open_option_premium, futures_margin,
                          peak_equity, current_equity)) or daily_loss_limit <= 0:
        return {"valid": False, "trading_permitted": False, "reasons": ["invalid balances"]}
    exposure = reserved_premium + open_option_premium
    drawdown = max(0, peak_equity - current_equity)
    daily_pnl = realized_pnl + unrealized_pnl
    reasons = []
    if exposure > 5000:
        reasons.append("live_option_premium_cap_exceeded")
    if futures_margin > cash:
        reasons.append("insufficient_margin")
    if daily_pnl <= -daily_loss_limit:
        reasons.append("daily_loss_limit_reached")
    if drawdown > 0.1 * peak_equity:
        reasons.append("drawdown_over_10_percent")
    return {"valid": True, "trading_permitted": False, "reasons": reasons,
            "option_premium_exposure": exposure, "drawdown_rupees": drawdown,
            "daily_pnl": daily_pnl, "note": "read-only; independent live risk gate required"}
