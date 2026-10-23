from Backend.application.options.execution_preflight import verify_premium_exposure
from Backend.application.options.option_buyer_limits import check_live_budget, OptionBuyerLimits


def test_preflight_rejects_malformed_numeric_values():
    for bad in (None, "nan", True, float("nan"), float("inf"), -1):
        assert not verify_premium_exposure(
            ask=bad, lot_size=65, lots=1, existing=0, pending=0, limit=5000)


def test_live_budget_rejects_malformed_exposure():
    for bad in (None, "nan", True, float("nan"), float("inf"), -1):
        result = check_live_budget(
            ask=50, lot_size=65, lots=1,
            existing_open_premium_rupees=bad,
            limits=OptionBuyerLimits(live_enabled=True))
        assert not result["eligible"]
        assert "invalid_exposure_or_quote" in result["reasons"]
