from Backend.application.agents.financial_risk_v2 import evaluate_account_risk


def test_account_risk_blocks_live_orders_even_if_metrics_clean():
    x = evaluate_account_risk(cash=10000, reserved_premium=100, open_option_premium=100,
        futures_margin=0, unrealized_pnl=0, realized_pnl=0, peak_equity=10000, current_equity=10000)
    assert x["valid"] and not x["trading_permitted"]


def test_exposure_and_loss_alerts():
    x = evaluate_account_risk(cash=10000, reserved_premium=4000, open_option_premium=2000,
        futures_margin=0, unrealized_pnl=-1500, realized_pnl=0, peak_equity=10000, current_equity=8000)
    assert "live_option_premium_cap_exceeded" in x["reasons"]
    assert "daily_loss_limit_reached" in x["reasons"]
