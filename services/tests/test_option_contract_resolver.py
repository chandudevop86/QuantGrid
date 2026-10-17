"""Option contract selection must fail closed and never submit an order."""
from datetime import datetime, timedelta, timezone

import pytest

from Backend.application.option_contract_resolver import OptionContractResolver, OptionSelectionError

NOW = datetime(2026, 10, 19, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))


def chain():
    return {
        "symbol": "NIFTY",
        "source": "dhan-option-chain",
        "provider_available": True,
        "live_rows_available": True,
        "data_quality": {"status": "PASS"},
        "updated_at": (NOW - timedelta(seconds=15)).isoformat(),
        "expiry": "2026-10-20",
        "atm_strike": 25000,
        "rows": [{"strike": 25000,
                  "ce": {"security_id": "12345", "bid": {"price": 109}, "ask": {"price": 110}, "volume": 4000},
                  "pe": {"security_id": "22345", "bid": {"price": 120}, "ask": {"price": 121}, "volume": 5000}}],
    }


@pytest.mark.parametrize("side,security_id", [("CE", "12345"), ("PE", "22345")])
def test_selects_atm_leg_as_candidate_not_order(side, security_id):
    result = OptionContractResolver().resolve(symbol="NIFTY", option_type=side, chain=chain(), now=NOW)
    assert result["security_id"] == security_id
    assert result["option_type"] == side
    assert result["strike"] == 25000
    assert result["exchange_segment"] == "NSE_FNO"
    assert result["execution_approved"] is False
    assert result["status"] == "candidate_only"
    assert result["chain_assembled_at"] == chain()["updated_at"]
    assert result["exchange_quote_timestamp_verified"] is False
    assert "quote_time" not in result


@pytest.mark.parametrize("field,value,reason", [
    ("source", "yahoo-finance-options", "unverified_option_chain"),
    ("provider_available", False, "unverified_option_chain"),
    ("data_quality", {"status": "DEGRADED"}, "unverified_option_chain"),
    ("expiry", "2026-10-18", "expired_option_contract"),
    ("updated_at", "2026-10-19T09:56:00+05:30", "stale_or_future_option_chain"),
])
def test_rejects_bad_chain(field, value, reason):
    payload = chain()
    payload[field] = value
    with pytest.raises(OptionSelectionError, match=reason):
        OptionContractResolver().resolve(symbol="NIFTY", option_type="CE", chain=payload, now=NOW)


def test_rejects_missing_security_id():
    payload = chain()
    payload["rows"][0]["ce"]["security_id"] = None
    with pytest.raises(OptionSelectionError, match="invalid_option_security_id"):
        OptionContractResolver().resolve(symbol="NIFTY", option_type="CE", chain=payload, now=NOW)


def test_rejects_wide_spread_and_missing_liquidity():
    payload = chain()
    payload["rows"][0]["pe"]["ask"]["price"] = 200
    with pytest.raises(OptionSelectionError, match="option_spread_too_wide"):
        OptionContractResolver().resolve(symbol="NIFTY", option_type="PE", chain=payload, now=NOW)
    payload = chain()
    payload["rows"][0]["pe"]["volume"] = 0
    with pytest.raises(OptionSelectionError, match="missing_or_invalid_volume"):
        OptionContractResolver().resolve(symbol="NIFTY", option_type="PE", chain=payload, now=NOW)


def test_rejects_missing_chain_instead_of_fabricating_contract():
    with pytest.raises(OptionSelectionError, match="verified_dhan_chain_required"):
        OptionContractResolver().resolve(symbol="NIFTY", option_type="CE", now=NOW)


def test_does_not_guess_option_type():
    with pytest.raises(OptionSelectionError, match="invalid_option_type"):
        OptionContractResolver().resolve(symbol="NIFTY", option_type="BUY", chain=chain(), now=NOW)
