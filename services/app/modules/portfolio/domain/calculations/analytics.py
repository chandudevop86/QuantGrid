from __future__ import annotations

import math
from dataclasses import dataclass

from app.modules.portfolio.domain.entities import HoldingSnapshot
from app.modules.portfolio.domain.exceptions import InsufficientDataError


@dataclass(slots=True)
class AllocationSlice:
    label: str
    value: float
    weight_percent: float


@dataclass(slots=True)
class HealthScoreBreakdown:
    overall_score: float  # 0-100
    diversification_component: float
    concentration_component: float
    volatility_component: float
    asset_mix_component: float
    notes: list[str]


class AnalyticsEngine:
    """Pure engine computing allocation breakdowns, diversification, and health scores."""

    @staticmethod
    def _total_market_value(holdings: list[HoldingSnapshot]) -> float:
        total = sum(h.market_value for h in holdings)
        if total <= 0:
            raise InsufficientDataError("Portfolio has no positive market value to analyze.")
        return total

    @classmethod
    def sector_allocation(cls, holdings: list[HoldingSnapshot]) -> list[AllocationSlice]:
        total = cls._total_market_value(holdings)
        buckets: dict[str, float] = {}
        for h in holdings:
            key = h.sector or "Unclassified"
            buckets[key] = buckets.get(key, 0.0) + h.market_value
        return sorted(
            [AllocationSlice(k, v, (v / total) * 100.0) for k, v in buckets.items()],
            key=lambda s: s.value, reverse=True,
        )

    @classmethod
    def market_cap_allocation(cls, holdings: list[HoldingSnapshot]) -> list[AllocationSlice]:
        total = cls._total_market_value(holdings)
        buckets: dict[str, float] = {}
        for h in holdings:
            key = h.market_cap_segment.value
            buckets[key] = buckets.get(key, 0.0) + h.market_value
        return sorted(
            [AllocationSlice(k, v, (v / total) * 100.0) for k, v in buckets.items()],
            key=lambda s: s.value, reverse=True,
        )

    @classmethod
    def asset_class_allocation(cls, holdings: list[HoldingSnapshot]) -> list[AllocationSlice]:
        total = cls._total_market_value(holdings)
        buckets: dict[str, float] = {}
        for h in holdings:
            key = h.asset_class.value
            buckets[key] = buckets.get(key, 0.0) + h.market_value
        return sorted(
            [AllocationSlice(k, v, (v / total) * 100.0) for k, v in buckets.items()],
            key=lambda s: s.value, reverse=True,
        )

    @classmethod
    def top_holdings(cls, holdings: list[HoldingSnapshot], limit: int = 5) -> list[AllocationSlice]:
        total = cls._total_market_value(holdings)
        ranked = sorted(holdings, key=lambda h: h.market_value, reverse=True)[:limit]
        return [
            AllocationSlice(h.symbol, h.market_value, (h.market_value / total) * 100.0)
            for h in ranked
        ]

    @classmethod
    def diversification_score(cls, holdings: list[HoldingSnapshot]) -> float:
        """
        Score from 0 (fully concentrated in one holding) to 100 (perfectly
        diversified), derived from the Herfindahl-Hirschman Index (HHI) of
        position weights.
        """
        total = cls._total_market_value(holdings)
        weights = [h.market_value / total for h in holdings]
        hhi = sum(w ** 2 for w in weights)
        n = len(holdings)
        if n <= 1:
            return 0.0
        # Normalize HHI (which ranges 1/n .. 1) onto a 0-100 scale where lower
        # concentration => higher diversification score.
        min_hhi = 1.0 / n
        normalized = (hhi - min_hhi) / (1.0 - min_hhi) if (1.0 - min_hhi) > 0 else 0.0
        return max(0.0, min(100.0, (1.0 - normalized) * 100.0))

    @classmethod
    def benchmark_comparison(cls, portfolio_return_percent: float,
                              benchmark_return_percent: float) -> dict[str, float]:
        return {
            "portfolio_return_percent": portfolio_return_percent,
            "benchmark_return_percent": benchmark_return_percent,
            "excess_return_percent": portfolio_return_percent - benchmark_return_percent,
            "outperforming": portfolio_return_percent > benchmark_return_percent,
        }

    @classmethod
    def health_score(cls, holdings: list[HoldingSnapshot], volatility_percent: float | None = None,
                      max_single_holding_warn_threshold: float = 25.0) -> HealthScoreBreakdown:
        """
        Composite 0-100 health score blending diversification, concentration
        risk, volatility, and asset-mix balance. Weights are intentionally
        explicit/documented rather than a black box.
        """
        notes: list[str] = []
        total = cls._total_market_value(holdings)

        diversification = cls.diversification_score(holdings)

        top = cls.top_holdings(holdings, limit=1)
        largest_weight = top[0].weight_percent if top else 0.0
        concentration_component = max(0.0, 100.0 - max(0.0, largest_weight - 10.0) * 2)
        if largest_weight > max_single_holding_warn_threshold:
            notes.append(
                f"Top holding represents {largest_weight:.1f}% of the portfolio, "
                f"above the {max_single_holding_warn_threshold:.0f}% concentration guideline."
            )

        if volatility_percent is None:
            volatility_component = 70.0
            notes.append("Volatility unavailable; used a neutral default for scoring.")
        else:
            # Lower annualized volatility -> higher score. 10% vol ~ 90 score, 40%+ vol ~ 10 score.
            volatility_component = max(0.0, min(100.0, 100.0 - (volatility_percent - 10.0) * 2))

        asset_classes = {h.asset_class for h in holdings}
        asset_mix_component = min(100.0, 40.0 + len(asset_classes) * 20.0)
        if len(asset_classes) == 1:
            notes.append("Portfolio is concentrated in a single asset class.")

        overall = (
            diversification * 0.35
            + concentration_component * 0.25
            + volatility_component * 0.25
            + asset_mix_component * 0.15
        )
        return HealthScoreBreakdown(
            overall_score=round(overall, 2),
            diversification_component=round(diversification, 2),
            concentration_component=round(concentration_component, 2),
            volatility_component=round(volatility_component, 2),
            asset_mix_component=round(asset_mix_component, 2),
            notes=notes,
        )
