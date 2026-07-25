from __future__ import annotations

from Backend.application.provider_consensus import (
    ProviderConsensus,
    ProviderSnapshot,
)



class ProviderConsensusEngine:
    """
    Cross-provider validation engine.

    Responsibilities
    ----------------
    • Compare multiple broker market feeds
    • Detect stale or invalid providers
    • Detect price mismatches
    • Score provider quality
    • Automatically perform provider failover
    • Return a final provider consensus
    """
    def __init__(
        self,
        providers: list,
    ):
        self.providers = providers

    def get_provider_snapshots(
    self,
    symbol: str,
    ) -> list[ProviderSnapshot]:

        snapshots = []

        for provider in self.providers:

            try:
                data = provider.get_quote(symbol)

                snapshot = ProviderSnapshot(
                    provider=provider.name,
                    symbol=symbol,
                    ltp=data["ltp"],
                    bid=data.get("bid"),
                    ask=data.get("ask"),
                    volume=data.get("volume"),
                    timestamp=data.get("timestamp"),
                    feed_delay_seconds=data.get(
                        "feed_delay_seconds",
                        0,
                    ),
                )

                snapshots.append(snapshot)

            except Exception as exc:

                snapshots.append(
                    ProviderSnapshot(
                        provider=provider.name,
                        symbol=symbol,
                        ltp=0.0,
                        healthy=False,
                        warnings=[
                            str(exc)
                        ],
                    )
                )

        return snapshots
    def validate_provider_health(
    self,
    snapshots: list[ProviderSnapshot],
    ) -> list[ProviderSnapshot]:

        for snapshot in snapshots:

            if snapshot.ltp <= 0:
                snapshot.healthy = False
                snapshot.warnings.append(
                    "invalid_ltp"
                )

            if snapshot.timestamp is None:
                snapshot.warnings.append(
                    "missing_timestamp"
                )

            if snapshot.latency_ms > 1000:
                snapshot.warnings.append(
                    "high_latency"
                )

            if len(snapshot.warnings) > 0:
                snapshot.confidence -= (
                    len(snapshot.warnings) * 10
                )

                if snapshot.confidence < 0:
                    snapshot.confidence = 0

        return snapshots

    def validate_live_suitability(
    self,
    snapshots: list[ProviderSnapshot],
    ) -> list[ProviderSnapshot]:
        
        """
    Validate providers for live execution.

    Rules:
    - Provider must be healthy
    - LTP must be valid
    - Feed delay must be acceptable
    - Confidence must be above threshold
    """

        for snapshot in snapshots:

            if not snapshot.healthy:
                snapshot.live_suitable = False
                snapshot.warnings.append(
                    "provider_unhealthy"
                )

            if snapshot.ltp <= 0:
                snapshot.live_suitable = False
                snapshot.warnings.append(
                    "invalid_market_price"
                )

            if snapshot.feed_delay_seconds > 5:
                snapshot.live_suitable = False
                snapshot.warnings.append(
                    "feed_delay_exceeded"
                )

            if snapshot.confidence < 50:
                snapshot.live_suitable = False
                snapshot.warnings.append(
                    "low_confidence"
                )

        return snapshots

    def compare_prices(
    self,
    snapshots: list[ProviderSnapshot],
    ) -> dict:
        """
    Compare LTP across providers.

    Returns:
    - average price
    - minimum price
    - maximum price
    - spread
    - difference percentage
    """

        prices = {
            snapshot.provider: snapshot.ltp
            for snapshot in snapshots
            if snapshot.healthy
        }

        if not prices:
            return {
                "status": "NO_DATA",
                "providers": {},
            }

        values = list(prices.values())

        minimum = min(values)
        maximum = max(values)

        average = sum(values) / len(values)

        spread = maximum - minimum

        difference_percent = (
            (spread / average) * 100
            if average
            else 0
        )

        return {
        "status": "OK",
        "providers": prices,
        "average_price": round(average, 2),
        "min_price": minimum,
        "max_price": maximum,
        "price_spread": round(spread, 2),
        "difference_percent": round(
            difference_percent,
            4,
        ),
    }

    def compare_bid_ask(
    self,
    snapshots: list[ProviderSnapshot],
    ) -> dict:
        """
    Compare bid/ask spread across providers.

    Calculates:
    - bid values
    - ask values
    - spread
    - average spread
    """

        result = {}

        spreads = []

        for snapshot in snapshots:

                if snapshot.bid is None or snapshot.ask is None:
                    continue

                spread = snapshot.ask - snapshot.bid

                spreads.append(spread)

                result[snapshot.provider] = {
                    "bid": snapshot.bid,
                    "ask": snapshot.ask,
                    "spread": round(spread, 2),
                }

        if not spreads:
                return {
                    "status": "NO_DATA",
                    "providers": {},
                }

        return {
                "status": "OK",
                "providers": result,
                "average_spread": round(
                    sum(spreads) / len(spreads),
                    2,
                ),
                "max_spread": round(
                    max(spreads),
                    2,
                ),
                "min_spread": round(
                    min(spreads),
                    2,
                ),
            }

    def compare_volume(
    self,
    snapshots: list[ProviderSnapshot],
    ) -> dict:
        """
    Compare volume across providers.
    """

        volumes = {}

        valid_volumes = []

        for snapshot in snapshots:

            if snapshot.volume is None:
                continue

            volumes[snapshot.provider] = snapshot.volume

            valid_volumes.append(
                snapshot.volume
            )

        if not valid_volumes:
            return {
                "status": "NO_DATA",
                "providers": {},
            }

        average_volume = (
            sum(valid_volumes) /
            len(valid_volumes)
        )

        deviations = {}

        for provider, volume in volumes.items():

            deviation = (
                abs(volume - average_volume)
                / average_volume
                * 100
                if average_volume
                else 0
            )

            deviations[provider] = round(
                deviation,
                2,
            )

        return {
            "status": "OK",
            "providers": volumes,
            "average_volume": round(
                average_volume,
                2,
            ),
            "deviation_percent": deviations,
        }

    def compare_timestamps(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> dict[str, Any]:
        ...

    def calculate_latency(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> dict[str, float]:
        ...

    def calculate_feed_delay(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> dict[str, int]:
        ...

    def calculate_provider_scores(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> dict[str, float]:
        ...

    def calculate_confidence(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> float:
        ...

    def select_best_provider(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> ProviderSnapshot:
        ...

    def perform_failover(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> ProviderSnapshot:
        ...

    def build_consensus(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> ProviderConsensus:
        ...