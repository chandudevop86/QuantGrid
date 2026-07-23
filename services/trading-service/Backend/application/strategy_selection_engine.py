from dataclasses import dataclass


@dataclass
class StrategySelectionInput:
    trend: str
    market_regime: str
    volatility: str
    volume: str
    oi_bias: str
    vwap_relation: str
    confidence: int
    risk_reward: float
    liquidity: str
    expiry_day: bool
    news_driven: bool


@dataclass
class StrategySelectionResult:
    strategy_name: str
    confidence: int
    reason: str
    alternatives: list[str]


class StrategySelector:

    def select(self, market: StrategySelectionInput) -> StrategySelectionResult:

        # Avoid trading during major news
        if market.news_driven:
            return StrategySelectionResult(
                strategy_name="no_trade",
                confidence=95,
                reason="Major news event detected",
                alternatives=["breakout"]
            )

        # Expiry Day
        if market.expiry_day:
            return StrategySelectionResult(
                strategy_name="btst",
                confidence=90,
                reason="Expiry day momentum",
                alternatives=["amd", "breakout"]
            )

        # Strong Trend
        if market.trend == "Strong Trend":
            return StrategySelectionResult(
                strategy_name="mtf",
                confidence=92,
                reason="Strong higher timeframe trend",
                alternatives=["breakout"]
            )

        # Trending Market
        if market.market_regime == "Trending":
            return StrategySelectionResult(
                strategy_name="breakout",
                confidence=88,
                reason="Trending market detected",
                alternatives=["mtf"]
            )

        # Range Bound
        if market.market_regime == "Range":
            return StrategySelectionResult(
                strategy_name="mean_reversion",
                confidence=85,
                reason="Range-bound market",
                alternatives=["amd"]
            )

        # Sideways
        if market.market_regime == "Sideways":
            return StrategySelectionResult(
                strategy_name="amd",
                confidence=80,
                reason="Low directional bias",
                alternatives=["mean_reversion"]
            )

        return StrategySelectionResult(
            strategy_name="breakout",
            confidence=60,
            reason="Default strategy",
            alternatives=["mtf", "mean_reversion"]
        )