class MarketRegimeConsensusEngine:
    """Multi-timeframe market regime detection engine."""

    def detect_trend(
        self,
        timeframe: str,
        candles: list[dict],
    ) -> TimeframeTrend:
        ...

    def detect_volatility(
        self,
        timeframe: str,
        candles: list[dict],
    ) -> dict[str, float]:
        ...

    def detect_market_structure(
        self,
        timeframe: str,
        candles: list[dict],
    ) -> dict[str, str]:
        ...

    def combine_timeframes(
        self,
        trends: list[TimeframeTrend],
    ) -> dict[str, float]:
        ...

    def calculate_alignment(
        self,
        trends: list[TimeframeTrend],
    ) -> float:
        ...

    def calculate_bias(
        self,
        trends: list[TimeframeTrend],
    ) -> str:
        ...

    def calculate_confidence(
        self,
        trends: list[TimeframeTrend],
    ) -> float:
        ...

    def recommend_strategy(
        self,
        regime: str,
        bias: str,
    ) -> str:
        ...

    def build_market_regime(
        self,
        candles_by_timeframe: dict[str, list[dict]],
    ) -> MarketRegime:
        ...