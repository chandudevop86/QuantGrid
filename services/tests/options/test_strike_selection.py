import pytest

from Backend.application.options.strike_selection import (
    Moneyness, classify_strike, evaluate_contract,
)


@pytest.mark.parametrize("side,strike,expected", [
    ("PE", 22450, Moneyness.ATM),
    ("PE", 22400, Moneyness.NEAR_ATM),
    ("PE", 22600, Moneyness.ITM),
    ("PE", 21600, Moneyness.DEEP_OTM),
    ("CE", 22600, Moneyness.OTM),
    ("CE", 21600, Moneyness.DEEP_ITM),
])
def test_moneyness(side, strike, expected):
    assert classify_strike(22455, strike, side) == expected


def test_invalid_input():
    with pytest.raises(ValueError):
        classify_strike(0, 21600, "PE")
    with pytest.raises(ValueError):
        classify_strike(22455, 21600, "BUY")


def test_eligible_contract():
    result = evaluate_contract(spot=22455, strike=22450, side="PE",
        bid=100, ask=101, open_interest=10000, delta=-0.49, quote_age_seconds=2)
    assert result["eligible"] is True


def test_deep_otm_rejected():
    result = evaluate_contract(spot=22455, strike=21600, side="PE",
        bid=2, ask=2.5, open_interest=10000, delta=-0.02, quote_age_seconds=2)
    assert not result["eligible"]
    assert "moneyness_not_allowed" in result["reasons"]


def test_missing_data_fails_closed():
    result = evaluate_contract(spot=22455, strike=22450, side="PE",
        bid=None, ask=None, open_interest=None, delta=None, quote_age_seconds=None)
    assert not result["eligible"]
    assert len(result["reasons"]) >= 4
