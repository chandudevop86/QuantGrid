import hashlib
import json
from datetime import date

import pytest

from Backend.application.options.contract_master_verification import ContractMasterVerificationError
from Backend.application.options.master_snapshot import verify_master_snapshot_contract

TODAY = date(2026, 10, 26)
ROW = {"security_id": "123456", "underlying": "NIFTY", "segment": "NSE_FNO",
       "expiry": "2026-10-29", "strike": 23000, "side": "CE", "lot_size": 65}


def digest(rows):
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def check(rows=None, **overrides):
    rows = [ROW.copy()] if rows is None else rows
    args = dict(rows=rows, expected_sha256=digest(rows), snapshot_date="2026-10-26",
                security_id="123456", expiry="2026-10-29", strike=23000,
                side="CE", lot_size=65, as_of=TODAY)
    args.update(overrides)
    return verify_master_snapshot_contract(**args)


def test_verified_snapshot_contract():
    assert check()["security_id"] == "123456"


def test_missing_independent_digest_fails_closed():
    with pytest.raises(ContractMasterVerificationError):
        check(expected_sha256="")


def test_modified_snapshot_fails_closed():
    with pytest.raises(ContractMasterVerificationError):
        check(expected_sha256=digest([ROW])[:-1] + "0" if digest([ROW])[-1] != "0" else digest([ROW])[:-1] + "1")


def test_stale_snapshot_fails_closed():
    with pytest.raises(ContractMasterVerificationError):
        check(snapshot_date="2026-10-25")


def test_duplicate_security_id_fails_closed():
    rows = [ROW.copy(), ROW.copy()]
    with pytest.raises(ContractMasterVerificationError):
        check(rows=rows)


def test_wrong_contract_fields_fail_closed():
    with pytest.raises(ContractMasterVerificationError):
        check(lot_size=75)
