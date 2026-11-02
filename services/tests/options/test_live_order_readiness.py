from datetime import datetime, timezone

from Backend.application.options.live_order_readiness import LiveOrderEvidence, assess_live_order_readiness


def test_default_is_blocked():
    result = assess_live_order_readiness(LiveOrderEvidence())
    assert not result["ready"]
    assert "live_feature_disabled" in result["blockers"]
    assert "atomic_capital_reservation_missing" in result["blockers"]
    assert result["broker_order_submitted"] is False


def test_complete_verified_evidence_passes_preflight_only():
    now = datetime(2026, 10, 30, 5, 0, tzinfo=timezone.utc)
    fields = {field: True for field in (
        "actor_authorized", "broker_authenticated", "kill_switch_off",
        "market_session_open", "contract_master_verified", "security_id_matches",
        "expiry_verified", "quote_provenance_verified", "atomic_reservation_available",
        "broker_order_idempotency_available", "order_reconciliation_available",
        "emergency_exit_available", "live_feature_enabled")}
    evidence = LiveOrderEvidence(**fields, quote_timestamp=now.isoformat(),
                                 contract_lot_size=65, exchange_lot_size=65,
                                 ask=50.0, lots=1)
    result = assess_live_order_readiness(evidence, now=now)
    assert result["ready"]
    assert result["broker_order_submitted"] is False


def test_budget_includes_pending_reservations():
    now = datetime(2026, 10, 30, 5, 0, tzinfo=timezone.utc)
    fields = {field: True for field in (
        "actor_authorized", "broker_authenticated", "kill_switch_off",
        "market_session_open", "contract_master_verified", "security_id_matches",
        "expiry_verified", "quote_provenance_verified", "atomic_reservation_available",
        "broker_order_idempotency_available", "order_reconciliation_available",
        "emergency_exit_available", "live_feature_enabled")}
    evidence = LiveOrderEvidence(**fields, quote_timestamp=now.isoformat(),
                                 contract_lot_size=65, exchange_lot_size=65,
                                 ask=50.0, lots=1, existing_exposure=1000,
                                 pending_reservations=1000)
    assert "exposure_invalid_or_exceeds_5000" in assess_live_order_readiness(evidence, now=now)["blockers"]
    assert "exposure_invalid_or_exceeds_5000" in assess_live_order_readiness(evidence, now=now, max_exposure=10000)["blockers"]
