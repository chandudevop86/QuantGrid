from datetime import datetime, timedelta, timezone

import pytest

from Backend.application.options.quote_freshness import (
    QuoteFreshnessError,
    verify_exchange_quote_timestamp,
)

NOW = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("timestamp", [
    None, "", 0, "2026-10-24T10:00:00", "not-a-date",
    "2026-10-24T09:59:29Z", "2026-10-24T10:00:01Z",
])
def test_missing_invalid_stale_and_future_exchange_quotes_fail_closed(timestamp):
    with pytest.raises(QuoteFreshnessError):
        verify_exchange_quote_timestamp(timestamp, now=NOW)


def test_exact_freshness_boundary_is_allowed():
    result = verify_exchange_quote_timestamp("2026-10-24T09:59:30Z", now=NOW)
    assert result == NOW - timedelta(seconds=30)


def test_offset_timestamp_is_normalized_to_utc():
    assert verify_exchange_quote_timestamp("2026-10-24T15:29:59+05:30", now=NOW) == NOW - timedelta(seconds=1)


def test_naive_validation_clock_is_rejected():
    with pytest.raises(QuoteFreshnessError):
        verify_exchange_quote_timestamp("2026-10-24T10:00:00Z", now=NOW.replace(tzinfo=None))


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_freshness_policy_rejected(limit):
    with pytest.raises(QuoteFreshnessError):
        verify_exchange_quote_timestamp("2026-10-24T10:00:00Z", now=NOW, max_age_seconds=limit)
