from datetime import date

import pytest

from Backend.application.options.contract_master_verification import (
    ContractMasterVerificationError,
    verify_nifty_option_contract,
)


def _master():
    return {"security_id": "123456", "underlying": "NIFTY", "segment": "NSE_FNO",
            "expiry": "2026-10-29", "strike": 23000, "side": "CE", "lot_size": 65}


def _check(row, **overrides):
    args = dict(master_row=row, security_id="123456", expiry="2026-10-29",
                strike=23000, side="CE", lot_size=65, as_of=date(2026, 10, 23))
    args.update(overrides)
    return verify_nifty_option_contract(**args)


def test_matching_authoritative_master_row():
    assert _check(_master())["lot_size"] == 65


@pytest.mark.parametrize("field,value", [
    ("security_id", "999"), ("underlying", "BANKNIFTY"),
    ("segment", "NSE_EQ"), ("expiry", "2026-11-05"),
    ("strike", 23100), ("side", "PE"), ("lot_size", 75),
])
def test_master_mismatch_fails_closed(field, value):
    row = _master()
    row[field] = value
    with pytest.raises(ContractMasterVerificationError):
        _check(row)


def test_missing_master_and_expired_contract_rejected():
    with pytest.raises(ContractMasterVerificationError):
        _check(None)
    with pytest.raises(ContractMasterVerificationError):
        _check(_master(), as_of=date(2026, 10, 30))


@pytest.mark.parametrize("lot", [True, 0, -1, 65.0])
def test_invalid_lot_type_rejected(lot):
    with pytest.raises(ContractMasterVerificationError):
        _check(_master(), lot_size=lot)
