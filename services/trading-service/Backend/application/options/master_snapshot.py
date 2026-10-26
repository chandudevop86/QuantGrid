"""Fail-closed integrity gate for externally acquired instrument-master snapshots.

The expected SHA-256 must come from an independent trusted configuration or
verification channel, NOT from the same downloaded snapshot. This does not
download Dhan instruments, authenticate the provider, or enable trading.
"""
import hashlib
import json
from datetime import date
from typing import Any

from Backend.application.options.contract_master_verification import (
    ContractMasterVerificationError,
    verify_nifty_option_contract,
)


def _canonical_bytes(rows: list[dict[str, Any]]) -> bytes:
    return json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def verify_master_snapshot_contract(*, rows: Any, expected_sha256: str,
                                    snapshot_date: str, security_id: str,
                                    expiry: str, strike: float, side: str,
                                    lot_size: int, as_of: date) -> dict[str, Any]:
    """Verify independent digest, observation date, uniqueness, and contract identity.

    A caller must supply an independently authenticated expected digest.
    Never derive it from untrusted downloaded rows in production.
    """
    if not isinstance(as_of, date) or isinstance(as_of, type(None)):
        raise ContractMasterVerificationError("validation date required")
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise ContractMasterVerificationError("trusted instrument-master rows required")
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_sha256)):
        raise ContractMasterVerificationError("independent trusted SHA-256 required")
    try:
        observed_date = date.fromisoformat(snapshot_date)
        digest = hashlib.sha256(_canonical_bytes(rows)).hexdigest()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractMasterVerificationError("invalid instrument-master snapshot") from exc
    if observed_date != as_of:
        raise ContractMasterVerificationError("instrument-master snapshot not dated today")
    if digest != expected_sha256:
        raise ContractMasterVerificationError("instrument-master snapshot integrity mismatch")
    matches = [row for row in rows if str(row.get("security_id", "")) == str(security_id)]
    if len(matches) != 1:
        raise ContractMasterVerificationError("contract ID missing or ambiguous in master")
    return verify_nifty_option_contract(
        master_row=matches[0], security_id=security_id, expiry=expiry,
        strike=strike, side=side, lot_size=lot_size, as_of=as_of,
    )
