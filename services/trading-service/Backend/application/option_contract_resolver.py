"""Fail-closed NIFTY option contract selection from verified Dhan quotes.

Selection is advisory only: this module never places orders, authorizes live
trading, or sizes positions. Execution must separately verify lot size, account
risk, broker-native protection, and broker authorization.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))
MAX_CHAIN_ASSEMBLY_AGE_SECONDS = 120
MAX_SPREAD_FRACTION = 0.03


class OptionSelectionError(ValueError):
    """No contract is eligible; caller must return No Trade."""


def _positive_number(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OptionSelectionError(f"missing_or_invalid_{name}") from exc
    if not isfinite(number) or number <= 0:
        raise OptionSelectionError(f"missing_or_invalid_{name}")
    return number


class OptionContractResolver:
    def resolve(
        self,
        *,
        symbol: str,
        option_type: str,
        strike_type: str = "ATM",
        expiry_type: str = "WEEKLY",
        chain: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Select ATM CE/PE quotes; never convert a spot signal into an order.

        Require an explicit, verified chain captured from Dhan. Never fall
        back to synthetic contracts, Yahoo, or assumed execution details.
        """
        if symbol.strip().upper() != "NIFTY":
            raise OptionSelectionError("unsupported_underlying")
        side = option_type.strip().upper()
        if side not in {"CE", "PE"}:
            raise OptionSelectionError("invalid_option_type")
        if strike_type.upper() != "ATM" or expiry_type.upper() != "WEEKLY":
            raise OptionSelectionError("unsupported_contract_selection")
        if not isinstance(chain, dict):
            raise OptionSelectionError("verified_dhan_chain_required")
        if (chain.get("symbol") or "").upper() != "NIFTY":
            raise OptionSelectionError("underlying_mismatch")
        if (chain.get("source") != "dhan-option-chain"
                or chain.get("live_rows_available") is not True
                or chain.get("provider_available") is not True
                or (chain.get("data_quality") or {}).get("status") != "PASS"):
            raise OptionSelectionError("unverified_option_chain")

        clock = now or datetime.now(timezone.utc)
        if clock.tzinfo is None:
            raise OptionSelectionError("timezone_aware_clock_required")
        try:
            observed_at = datetime.fromisoformat(str(chain["updated_at"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError) as exc:
            raise OptionSelectionError("missing_chain_timestamp") from exc
        if observed_at.tzinfo is None:
            raise OptionSelectionError("chain_timestamp_without_timezone")
        age_seconds = (clock - observed_at).total_seconds()
        if not (0 <= age_seconds <= MAX_CHAIN_ASSEMBLY_AGE_SECONDS):
            raise OptionSelectionError("stale_or_future_option_chain")

        try:
            expiry = datetime.strptime(str(chain["expiry"]), "%Y-%m-%d").date()
        except (KeyError, TypeError, ValueError) as exc:
            raise OptionSelectionError("invalid_option_expiry") from exc
        if expiry < clock.astimezone(IST).date():
            raise OptionSelectionError("expired_option_contract")
        atm = int(_positive_number(chain.get("atm_strike"), "atm_strike"))
        rows = chain.get("rows")
        if not isinstance(rows, list):
            raise OptionSelectionError("missing_option_rows")
        candidates = [
            row for row in rows if isinstance(row, dict)
            and str(row.get("strike")) in {str(atm), f"{atm}.0"}
        ]
        if len(candidates) != 1:
            raise OptionSelectionError("missing_or_ambiguous_atm_strike")
        leg = candidates[0].get(side.lower())
        if not isinstance(leg, dict):
            raise OptionSelectionError("missing_option_leg")
        security_id = str(leg.get("security_id") or "").strip()
        if not security_id.isascii() or not security_id.isdecimal() or int(security_id) <= 0 or security_id == "13":
            raise OptionSelectionError("invalid_option_security_id")

        bid_field, ask_field = leg.get("bid"), leg.get("ask")
        bid = _positive_number(bid_field.get("price") if isinstance(bid_field, dict) else None, "bid")
        ask = _positive_number(ask_field.get("price") if isinstance(ask_field, dict) else None, "ask")
        volume = _positive_number(leg.get("volume"), "volume")
        if bid > ask or (ask - bid) / ask > MAX_SPREAD_FRACTION:
            raise OptionSelectionError("option_spread_too_wide")
        return {
            "status": "candidate_only",
            "symbol": "NIFTY",
            "option_type": side,
            "strike": atm,
            "expiry": expiry.isoformat(),
            "security_id": security_id,
            "exchange_segment": "NSE_FNO",
            "instrument_type": "OPTIDX",
            "bid": round(bid, 2),
            "ask": round(ask, 2),
            "volume": int(volume),
            "spread_fraction": round((ask - bid) / ask, 6),
            "quote_source": "dhan-option-chain",
            # Dhan option-chain response has no per-leg exchange quote timestamp.
            # This is API assembly time only and NEVER execution freshness proof.
            "chain_assembled_at": observed_at.isoformat(),
            "exchange_quote_timestamp_verified": False,
            "execution_approved": False,
            "execution_blocker": "lot_size_risk_and_protected_exit_not_yet_verified",
        }
