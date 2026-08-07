from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class ProviderSnapshot:
    """Snapshot of market data returned by a single provider."""

    provider: str
    symbol: str

    ltp: float
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None

    timestamp: datetime | None = None
    feed_delay_seconds: int = 0

    exchange: str = "NSE"

    healthy: bool = True
    live_suitable: bool = True

    latency_ms: float = 0.0

    confidence: float = 100.0

    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderConsensus:
    """Final consensus after validating all providers."""

    accepted: bool = False

    consensus_price: float | None = None
    selected_provider: str | None = None

    confidence: float = 0.0

    provider_count: int = 0
    healthy_provider_count: int = 0

    agreement_percent: float = 0.0

    price_spread: float = 0.0
    max_difference: float = 0.0

    feed_status: str = "UNKNOWN"

    failover_used: bool = False

    average_price: float | None = None
    median_price: float | None = None

    provider_scores: dict[str, float] = field(default_factory=dict)

    warnings: list[str] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    rejected_providers: list[str] = field(default_factory=list)

    snapshots: list[ProviderSnapshot] = field(default_factory=list)

    generated_at: datetime = field(
    default_factory=lambda: datetime.now(timezone.utc)
)
    diagnostics: dict[str, Any] = field(default_factory=dict)