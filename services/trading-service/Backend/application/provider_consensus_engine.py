from __future__ import annotations

from pytz import timezone

from Backend.application.provider_consensus import (
    ProviderConsensus,
    ProviderSnapshot,
)
from datetime import datetime,timezone 
import logging

logger = logging.getLogger(__name__)

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
            health = provider.health_check()
            
            if health.get("configured") is False:
                continue

            try:
                data = provider.get_ltp(symbol)

                snapshot = ProviderSnapshot(
                    provider=provider.provider_name,
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
                    logger.exception(
                        "Provider failed: %s",
                        provider.provider_name
                    )

                    snapshots.append(
                    ProviderSnapshot(
                        provider=provider.provider_name,
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
    ) -> dict:
        """
    Compare provider timestamps.
    """

        timestamps = {}

        valid_times = []

        for snapshot in snapshots:

            if snapshot.timestamp is None:
                continue

            timestamp = snapshot.timestamp

            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                )
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(
                    tzinfo=timezone.utc
                )    

            timestamps[snapshot.provider] = timestamp

            valid_times.append(timestamp)

        if not valid_times:
            return {
                "status": "NO_DATA",
                "providers": {},
            }

        latest = max(valid_times)
        oldest = min(valid_times)

        difference_seconds = (
            latest - oldest
        ).total_seconds()

        return {
            "status": "OK",
            "providers": timestamps,
            "latest_timestamp": latest,
            "oldest_timestamp": oldest,
            "difference_seconds": round(
                difference_seconds,
                3,
            ),
        }
    def calculate_latency(
    self,
    snapshots: list[ProviderSnapshot],
    ) -> dict:
        """
    Calculate provider latency statistics.

    Returns:
    - latency per provider
    - average latency
    - fastest provider
    - slowest provider
    """

        latencies = {}

        valid_latencies = []

        for snapshot in snapshots:

            latency = snapshot.latency_ms

            latencies[snapshot.provider] = latency

            valid_latencies.append(latency)


        if not valid_latencies:
            return {
                "status": "NO_DATA",
                "providers": {},
            }


        average_latency = (
            sum(valid_latencies)
            /
            len(valid_latencies)
        )


        fastest_provider = min(
            latencies,
            key=latencies.get,
        )

        slowest_provider = max(
            latencies,
            key=latencies.get,
        )


        return {
            "status": "OK",
            "providers": latencies,
            "average_latency_ms": round(
                average_latency,
                2,
            ),
            "fastest_provider": fastest_provider,
            "slowest_provider": slowest_provider,
        }

    def calculate_feed_delay(
    self,
    snapshots: list[ProviderSnapshot],
    ) -> dict:
        """
    Calculate feed delay statistics.

    Returns:
    - delay per provider
    - average delay
    - maximum delay
    - stale providers
    """

        delays = {}

        valid_delays = []

        stale_providers = []


        for snapshot in snapshots:

            delay = snapshot.feed_delay_seconds

            delays[snapshot.provider] = delay

            valid_delays.append(delay)


            if delay > 5:
                stale_providers.append(
                    snapshot.provider
                )


        if not valid_delays:
            return {
                "status": "NO_DATA",
                "providers": {},
            }


        average_delay = (
            sum(valid_delays)
            /
            len(valid_delays)
        )


        return {
            "status": "OK",
            "providers": delays,
            "average_delay_seconds": round(
                average_delay,
                2,
            ),
            "max_delay_seconds": max(
                valid_delays
            ),
            "stale_providers": stale_providers,
        }

    def calculate_provider_scores(
    self,
    snapshots: list[ProviderSnapshot],
    ) -> dict[str, float]:
        """
    Calculate provider reliability score.

    Score range:
    0 - 100

    Factors:
    - Healthy provider        +40
    - Live suitable           +30
    - Confidence contribution +20
    - Latency penalty
    - Feed delay penalty
    """

        scores: dict[str, float] = {}

        for snapshot in snapshots:

            score = 0.0


            # Health score
            if snapshot.healthy:
                score += 40


            # Live execution suitability
            if snapshot.live_suitable:
                score += 30


            # Confidence contribution
            score += (
                snapshot.confidence * 0.20
            )


            # Latency penalty
            if snapshot.latency_ms > 1000:
                score -= 20

            elif snapshot.latency_ms > 500:
                score -= 10


            # Feed delay penalty
            if snapshot.feed_delay_seconds > 10:
                score -= 25

            elif snapshot.feed_delay_seconds > 5:
                score -= 15


            # Warning penalty
            score -= (
                len(snapshot.warnings) * 5
            )


            # Clamp score
            score = max(
                0,
                min(score, 100)
            )


            scores[snapshot.provider] = round(
                score,
                2,
            )


        return scores

    def calculate_confidence(
    self,
    snapshots: list[ProviderSnapshot],
    ) -> float:
        """
    Calculate overall consensus confidence.

    Returns:
        Confidence score 0-100
    """

        if not snapshots:
            return 0.0


        healthy_count = sum(
            1
            for snapshot in snapshots
            if snapshot.healthy
        )


        healthy_ratio = (
            healthy_count / len(snapshots)
        )


        average_provider_confidence = (
            sum(
                snapshot.confidence
                for snapshot in snapshots
            )
            /
            len(snapshots)
        )


        agreement_score = 100.0


        prices = [
            snapshot.ltp
            for snapshot in snapshots
            if snapshot.healthy
        ]


        if len(prices) > 1:

            max_price = max(prices)
            min_price = min(prices)

            spread = max_price - min_price

            average_price = (
                sum(prices)
                /
                len(prices)
            )


            if average_price:

                difference_percent = (
                    spread /
                    average_price
                    *
                    100
                )

                agreement_score = max(
                    0,
                    100 - (difference_percent * 10)
                )


        confidence = (
            (healthy_ratio * 40)
            +
            (average_provider_confidence * 0.30)
            +
            (agreement_score * 0.30)
        )


        return round(
            min(confidence, 100),
            2,
        )

    def select_best_provider(
    self,
    snapshots: list[ProviderSnapshot],
    ) -> ProviderSnapshot:
        """
    Select highest scoring provider.
    """

        if not snapshots:
            raise ValueError(
                "No provider snapshots available"
            )


        scores = self.calculate_provider_scores(
            snapshots
        )


        eligible = [
            snapshot
            for snapshot in snapshots
            if snapshot.healthy
            and snapshot.live_suitable
            and snapshot.ltp > 0
        ]


        if not eligible:
            raise RuntimeError(
                "No suitable provider available"
            )


        best_provider = max(
            eligible,
            key=lambda snapshot:
                scores.get(
                    snapshot.provider,
                    0,
                ),
        )


        best_provider.diagnostics.update(
            {
                "provider_score":
                    scores.get(
                        best_provider.provider,
                        0,
                    )
            }
        )


        return best_provider

    def perform_failover(
    self,
    snapshots: list[ProviderSnapshot],
    ) -> ProviderSnapshot:
        """
    Select backup provider when primary fails.
    """

        if not snapshots:
            raise ValueError(
                "No provider snapshots available"
            )


        scores = self.calculate_provider_scores(
            snapshots
        )


        available = [
            snapshot
            for snapshot in snapshots
            if snapshot.healthy
            and snapshot.live_suitable
            and snapshot.ltp > 0
        ]


        if not available:
            raise RuntimeError(
                "No failover provider available"
            )


        selected = sorted(
            available,
            key=lambda snapshot:
                scores.get(
                    snapshot.provider,
                    0,
                ),
            reverse=True,
        )[0]


        selected.diagnostics.update(
            {
                "failover_selected": True,
                "provider_score":
                    scores.get(
                        selected.provider,
                        0,
                    ),
            }
        )


        return selected

    def build_consensus(
    self,
    symbol: str,
    ) -> ProviderConsensus:
        """
    Main consensus pipeline.

    Flow:
    1. Collect provider snapshots
    2. Validate health
    3. Validate live suitability
    4. Compare market feeds
    5. Score providers
    6. Calculate confidence
    7. Select best provider
    8. Return consensus
    """

        snapshots = self.get_provider_snapshots(
            symbol
        )


        snapshots = self.validate_provider_health(
            snapshots
        )


        snapshots = self.validate_live_suitability(
            snapshots
        )


        price_data = self.compare_prices(
            snapshots
        )

        bid_ask_data = self.compare_bid_ask(
            snapshots
        )

        volume_data = self.compare_volume(
            snapshots
        )

        timestamp_data = self.compare_timestamps(
            snapshots
        )


        latency_data = self.calculate_latency(
            snapshots
        )

        feed_delay_data = self.calculate_feed_delay(
            snapshots
        )


        scores = self.calculate_provider_scores(
            snapshots
        )


        confidence = self.calculate_confidence(
            snapshots
        )


        try:

            selected = self.select_best_provider(
                snapshots
            )

            failover_used = False


        except RuntimeError:

            selected = self.perform_failover(
                snapshots
            )

            failover_used = True



        healthy_count = sum(
            1
            for snapshot in snapshots
            if snapshot.healthy
        )


        prices = [
            snapshot.ltp
            for snapshot in snapshots
            if snapshot.healthy
        ]


        average_price = (
            sum(prices) / len(prices)
            if prices
            else None
        )

        if selected is None:
            raise RuntimeError(
                "No provider selected"
            )

        if selected.ltp <= 0:
            raise RuntimeError(
                f"Invalid consensus price from {selected.provider}"
            )
        return ProviderConsensus(

            accepted=confidence >= 70,
            
            consensus_price=selected.ltp,

            selected_provider=selected.provider,

            confidence=confidence,

            provider_count=len(
                snapshots
            ),

            healthy_provider_count=healthy_count,

            average_price=average_price,

            provider_scores=scores,

            failover_used=failover_used,

            snapshots=snapshots,

            diagnostics={
                "price": price_data,
                "bid_ask": bid_ask_data,
                "volume": volume_data,
                "timestamps": timestamp_data,
                "latency": latency_data,
                "feed_delay": feed_delay_data,
            },

        )