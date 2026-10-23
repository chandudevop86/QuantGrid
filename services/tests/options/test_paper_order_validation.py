from datetime import datetime, timedelta, timezone

from Backend.application.options.paper_order_validation import validate_option_paper_order


def payload():
    return dict(symbol="NIFTY", side="PE", spot=22455, strike=22450,
                expiry=(datetime.now(timezone.utc)+timedelta(days=2)).date().isoformat(),
                security_id="12345", bid=100, ask=101, open_interest=5000,
                delta=-0.5, quote_timestamp=datetime.now(timezone.utc).isoformat(),
                lot_size=65, lots=1)


def test_valid_preview_does_not_execute():
    result = validate_option_paper_order(**payload())
    assert result["eligible"]
    assert result["execution_enabled"] is False
    assert result["estimated_premium_rupees"] == 6565


def test_live_mode_rejected():
    assert "live_execution_forbidden" in validate_option_paper_order(**{**payload(), "execution_mode": "live"})["reasons"]


def test_missing_identity_and_expiry_rejected():
    result = validate_option_paper_order(**{**payload(), "security_id": "", "expiry": "bad"})
    assert not result["eligible"]
    assert "missing_contract_identity" in result["reasons"]


def test_stale_quote_rejected():
    stale = (datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
    assert "stale_quote" in validate_option_paper_order(**{**payload(), "quote_timestamp": stale})["reasons"]


def test_premium_limit_rejected():
    assert "premium_risk_limit_exceeded" in validate_option_paper_order(**{**payload(), "lots": 3})["reasons"]


def test_deep_otm_rejected():
    assert not validate_option_paper_order(**{**payload(), "strike": 21600})["eligible"]
