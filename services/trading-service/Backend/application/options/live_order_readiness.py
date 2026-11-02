"""Fail-closed live-option execution readiness policy.

This module does not send broker orders or enable live trading. All evidence
must be verified server-side; client flags are never authoritative.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

from .execution_preflight import verify_lot_size, verify_premium_exposure, verify_quote_freshness


@dataclass(frozen=True)
class LiveOrderEvidence:
    actor_authorized: bool = False
    broker_authenticated: bool = False
    kill_switch_off: bool = False
    market_session_open: bool = False
    contract_master_verified: bool = False
    security_id_matches: bool = False
    expiry_verified: bool = False
    quote_provenance_verified: bool = False
    quote_timestamp: str | None = None
    contract_lot_size: int = 0
    exchange_lot_size: int = 0
    ask: float = 0.0
    lots: int = 0
    existing_exposure: float = 0.0
    pending_reservations: float = 0.0
    atomic_reservation_available: bool = False
    broker_order_idempotency_available: bool = False
    order_reconciliation_available: bool = False
    emergency_exit_available: bool = False
    live_feature_enabled: bool = False


def assess_live_order_readiness(evidence: LiveOrderEvidence, *, now=None, max_exposure=5000.0):
    """Return actionable blockers. Never treat a successful preflight as an order."""
    checks = {
        "live_feature_disabled": evidence.live_feature_enabled,
        "actor_not_authorized": evidence.actor_authorized,
        "broker_not_authenticated": evidence.broker_authenticated,
        "kill_switch_active_or_unverified": evidence.kill_switch_off,
        "market_session_closed_or_unverified": evidence.market_session_open,
        "contract_master_unverified": evidence.contract_master_verified,
        "security_id_mismatch_or_unverified": evidence.security_id_matches,
        "expiry_unverified": evidence.expiry_verified,
        "quote_provenance_unverified": evidence.quote_provenance_verified,
        "quote_stale_or_unverified": verify_quote_freshness(evidence.quote_timestamp, now=now),
        "lot_size_mismatch": verify_lot_size(contract_lot_size=evidence.contract_lot_size, exchange_lot_size=evidence.exchange_lot_size),
        "invalid_lot_count": type(evidence.lots) is int and evidence.lots == 1,
        "atomic_capital_reservation_missing": evidence.atomic_reservation_available,
        "broker_order_idempotency_missing": evidence.broker_order_idempotency_available,
        "broker_reconciliation_missing": evidence.order_reconciliation_available,
        "emergency_exit_missing": evidence.emergency_exit_available,
    }
    valid_limit = type(max_exposure) in (int, float) and isfinite(max_exposure) and 0 < max_exposure <= 5000
    checks["exposure_invalid_or_exceeds_5000"] = valid_limit and verify_premium_exposure(
        ask=evidence.ask, lot_size=evidence.exchange_lot_size, lots=evidence.lots,
        existing=evidence.existing_exposure, pending=evidence.pending_reservations,
        limit=max_exposure if valid_limit else 0,
    )
    blockers = [reason for reason, passed in checks.items() if passed is not True]
    return {"ready": not blockers, "blockers": blockers, "max_live_exposure_rupees": 5000.0,
            "broker_order_submitted": False}
