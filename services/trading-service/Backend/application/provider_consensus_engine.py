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

    def get_provider_snapshots(
        self,
        symbol: str,
    ) -> list[ProviderSnapshot]:
        ...

    def validate_provider_health(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> list[ProviderSnapshot]:
        ...

    def validate_live_suitability(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> list[ProviderSnapshot]:
        ...

    def compare_prices(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> dict[str, float]:
        ...

    def compare_bid_ask(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> dict[str, Any]:
        ...

    def compare_volume(
        self,
        snapshots: list[ProviderSnapshot],
    ) -> dict[str, Any]:
        ...

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