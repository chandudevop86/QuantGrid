from Backend.application.compliance.client_launch_gate import (
    REQUIRED, assess_client_launch_readiness,
)


def test_no_evidence_blocks_client_launch():
    result = assess_client_launch_readiness({})
    assert not result["ready"]
    assert not result["activation_allowed"]
    assert "exchange_algo_approval_verified" in result["missing"]


def test_all_claimed_evidence_does_not_activate_live_trading():
    result = assess_client_launch_readiness({name: True for name in REQUIRED})
    assert result["ready"]
    assert not result["activation_allowed"]


def test_non_boolean_evidence_rejected():
    result = assess_client_launch_readiness({"legal_entity_reviewed": "true"})
    assert "legal_entity_reviewed" in result["missing"]


def test_unknown_business_mode_denied():
    assert not assess_client_launch_readiness({}, requested_mode="broker")["activation_allowed"]
