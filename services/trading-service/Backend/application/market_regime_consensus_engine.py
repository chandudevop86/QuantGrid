from Backend.application.market_regime_consensus import (
    TimeframeTrend,
    MarketRegime,
)



class MarketRegimeConsensusEngine:
    """Multi-timeframe market regime detection engine."""

    def detect_trend(
        self,
        timeframe: str,
        candles: list[dict],
        ) -> TimeframeTrend:
            """
        Detect trend direction for a timeframe.

        Uses:
        - EMA alignment
        - price movement
        - simple trend strength
        """

            if len(candles) < 20:
                return TimeframeTrend(
                    timeframe=timeframe,
                    trend="SIDEWAYS",
                    confidence=0.0,
                    diagnostics={
                        "reason": "insufficient candles"
                    },
                )


            closes = [
                float(c["close"])
                for c in candles
            ]


            # EMA calculation
            def ema(values: list[float], period: int) -> float:
                multiplier = 2 / (period + 1)

                result = values[0]

                for price in values[1:]:
                    result = (
                        (price - result)
                        * multiplier
                        + result
                    )

                return result


            ema_fast = ema(
                closes[-20:],
                5,
            )

            ema_slow = ema(
                closes[-20:],
                20,
            )


            current_price = closes[-1]


            if ema_fast > ema_slow and current_price > ema_fast:

                trend = "BULLISH"

            elif ema_fast < ema_slow and current_price < ema_fast:

                trend = "BEARISH"

            else:

                trend = "SIDEWAYS"


            strength = abs(
                ema_fast - ema_slow
            ) / ema_slow * 100


            confidence = min(
                strength * 20,
                100,
            )


            return TimeframeTrend(
                timeframe=timeframe,

                trend=trend,

                confidence=round(
                    confidence,
                    2,
                ),

                ema_alignment=(
                    ema_fast > ema_slow
                ),

                trend_strength=round(
                    strength,
                    2,
                ),

                diagnostics={
                    "ema_fast": round(
                        ema_fast,
                        2,
                    ),

                    "ema_slow": round(
                        ema_slow,
                        2,
                    ),

                    "current_price": current_price,
                },
            )
    def detect_volatility(
    self,
    timeframe: str,
    candles: list[dict],
    ) -> dict[str, float]:
        """
    Detect volatility.

    Uses:
    - ATR style range calculation
    - Average candle movement
    """

        if len(candles) < 2:
            return {
                "atr": 0.0,
                "volatility_percent": 0.0,
            }


        ranges = []

        for candle in candles[-20:]:

            high = float(candle["high"])

            low = float(candle["low"])

            close = float(candle["close"])


            ranges.append(
                high - low
            )


        atr = (
            sum(ranges)
            /
            len(ranges)
        )


        current_price = float(
            candles[-1]["close"]
        )


        volatility_percent = (
            atr /
            current_price
            *
            100
            if current_price
            else 0
        )


        return {
            "timeframe": timeframe,

            "atr": round(
                atr,
                2,
            ),

            "volatility_percent": round(
                volatility_percent,
                2,
            ),

            "level": (
                "HIGH"
                if volatility_percent > 1
                else
                "LOW"
            ),
        }

    def detect_market_structure(
    self,
    timeframe: str,
    candles: list[dict],
    ) -> dict[str, str]:
        """
    Detect market structure.

    Checks:
    - Higher highs
    - Higher lows
    - Lower highs
    - Lower lows
    - Breakout / Breakdown
    """

        if len(candles) < 10:
            return {
                "timeframe": timeframe,
                "structure": "UNKNOWN",
            }


        highs = [
            float(c["high"])
            for c in candles[-10:]
        ]

        lows = [
            float(c["low"])
            for c in candles[-10:]
        ]


        current_high = highs[-1]
        current_low = lows[-1]


        previous_high = max(
            highs[:-1]
        )

        previous_low = min(
            lows[:-1]
        )


        if current_high > previous_high:

            structure = "BREAKOUT"


        elif current_low < previous_low:

            structure = "BREAKDOWN"


        else:

            higher_highs = (
                highs[-1] > highs[-3]
            )

            higher_lows = (
                lows[-1] > lows[-3]
            )


            lower_highs = (
                highs[-1] < highs[-3]
            )

            lower_lows = (
                lows[-1] < lows[-3]
            )


            if higher_highs and higher_lows:

                structure = "UPTREND_STRUCTURE"


            elif lower_highs and lower_lows:

                structure = "DOWNTREND_STRUCTURE"


            else:

                structure = "RANGE"


        return {
            "timeframe": timeframe,

            "structure": structure,

            "current_high": current_high,

            "current_low": current_low,

            "previous_high": previous_high,

            "previous_low": previous_low,
        }

    def combine_timeframes(
    self,
    trends: list[TimeframeTrend],
    ) -> dict[str, float]:
        """
    Combine multiple timeframe trends.

    Returns:
    - bullish percentage
    - bearish percentage
    - sideways percentage
    - average confidence
    """

        if not trends:
            return {
                "bullish_percent": 0.0,
                "bearish_percent": 0.0,
                "sideways_percent": 0.0,
                "average_confidence": 0.0,
            }


        total = len(trends)


        bullish = sum(
            1
            for trend in trends
            if trend.trend == "BULLISH"
        )


        bearish = sum(
            1
            for trend in trends
            if trend.trend == "BEARISH"
        )


        sideways = sum(
            1
            for trend in trends
            if trend.trend == "SIDEWAYS"
        )


        average_confidence = (
            sum(
                trend.confidence
                for trend in trends
            )
            /
            total
        )


        return {
            "bullish_percent": round(
                bullish / total * 100,
                2,
            ),

            "bearish_percent": round(
                bearish / total * 100,
                2,
            ),

            "sideways_percent": round(
                sideways / total * 100,
                2,
            ),

            "average_confidence": round(
                average_confidence,
                2,
            ),

            "timeframes": total,
        }

    def calculate_alignment(
    self,
    trends: list[TimeframeTrend],
    ) -> float:
        """
    Calculate multi timeframe trend alignment.

    Returns:
        0 - 100 percentage
    """

        if not trends:
            return 0.0


        trend_count = len(trends)


        bullish = sum(
            1
            for t in trends
            if t.trend == "BULLISH"
        )


        bearish = sum(
            1
            for t in trends
            if t.trend == "BEARISH"
        )


        sideways = sum(
            1
            for t in trends
            if t.trend == "SIDEWAYS"
        )


        highest_alignment = max(
            bullish,
            bearish,
            sideways,
        )


        alignment = (
            highest_alignment
            /
            trend_count
            *
            100
        )


        return round(
            alignment,
            2,
        )

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