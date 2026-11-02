"""Retail algo release gate for QuantGrid (policy, not broker approval).

All approvals must be verified server-side against authenticated records.
This pure policy evaluator NEVER authorizes live execution by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class AlgoReleaseRequest:
    tenant_id: str
    broker_account_id: str
    strategy_id: str
    strategy_version: str
    exchange_algo_id: str
    order_idempotency_key: str


REQUIRED_CONTROLS = (
    "tenant_authenticated",
    "account_owned_by_tenant",
    "broker_authorization_verified",
    "broker_hosting_approved",
    "exchange_strategy_registration_verified",
    "strategy_version_approved",
    "exchange_algo_tag_verified",
    "broker_order_route_approved",
    "client_consent_verified",
    "market_data_licensed",
    "contract_master_fresh",
    "quote_fresh",
    "risk_limits_verified",
    "broker_reconciliation_healthy",
    "kill_switch_clear",
    "audit_storage_healthy",
)


def evaluate_algo_release(request: AlgoReleaseRequest, controls: Mapping[str, object] | None):
    """Return missing gates; even all True cannot bypass order execution service."""
    if not isinstance(request, AlgoReleaseRequest):
        return {"ready_for_review": False, "execution_authorized": False,
                "missing": list(REQUIRED_CONTROLS), "reason": "invalid request"}
    identifiers = (
        request.tenant_id, request.broker_account_id, request.strategy_id,
        request.strategy_version, request.exchange_algo_id, request.order_idempotency_key,
    )
    if any(not isinstance(v, str) or not v.strip() or len(v) > 128 for v in identifiers):
        return {"ready_for_review": False, "execution_authorized": False,
                "missing": list(REQUIRED_CONTROLS), "reason": "invalid identifiers"}
    if not isinstance(controls, Mapping):
        return {"ready_for_review": False, "execution_authorized": False,
                "missing": list(REQUIRED_CONTROLS), "reason": "invalid evidence"}
    missing = [name for name in REQUIRED_CONTROLS if controls.get(name) is not True]
    return {
        "ready_for_review": not missing,
        "execution_authorized": False,
        "missing": missing,
        "reason": ("requires independent server-side authorization and broker order gate"
                   if not missing else "mandatory release evidence missing"),
    }
