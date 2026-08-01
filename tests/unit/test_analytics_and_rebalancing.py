from __future__ import annotations

import pytest

from app.modules.portfolio.domain.calculations.analytics import AnalyticsEngine
from app.modules.portfolio.domain.calculations.rebalancing import RebalancingEngine
from app.modules.portfolio.domain.entities import HoldingSnapshot
from app.modules.portfolio.domain.enums import AssetClass, MarketCapSegment
from app.modules.portfolio.domain.exceptions import InsufficientDataError


def _snapshot(symbol, qty, cost, price, sector=None, asset_class=AssetClass.EQUITY,
              cap=MarketCapSegment.LARGE_CAP) -> HoldingSnapshot:
    return HoldingSnapshot(
        symbol=symbol, quantity=qty, average_cost=cost, current_price=price,
        sector=sector, asset_class=asset_class, market_cap_segment=cap,
    )


def test_sector_allocation_sums_to_100_percent():
    holdings = [
        _snapshot("AAPL", 10, 100, 150, sector="Technology"),
        _snapshot("JPM", 10, 100, 100, sector="Financials"),
    ]
    slices = AnalyticsEngine.sector_allocation(holdings)
    total_weight = sum(s.weight_percent for s in slices)
    assert total_weight == pytest.approx(100.0)


def test_top_holdings_ranked_by_market_value():
    holdings = [
        _snapshot("AAPL", 10, 100, 150),  # 1500
        _snapshot("MSFT", 5, 100, 100),  # 500
    ]
    top = AnalyticsEngine.top_holdings(holdings, limit=1)
    assert top[0].label == "AAPL"


def test_diversification_score_perfect_for_equal_weights():
    holdings = [_snapshot(f"SYM{i}", 10, 100, 100) for i in range(5)]
    score = AnalyticsEngine.diversification_score(holdings)
    assert score == pytest.approx(100.0, abs=0.01)


def test_diversification_score_zero_for_single_holding():
    holdings = [_snapshot("AAPL", 10, 100, 150)]
    score = AnalyticsEngine.diversification_score(holdings)
    assert score == 0.0


def test_health_score_within_bounds():
    holdings = [
        _snapshot("AAPL", 10, 100, 150, sector="Technology"),
        _snapshot("JPM", 10, 100, 100, sector="Financials", asset_class=AssetClass.EQUITY),
    ]
    breakdown = AnalyticsEngine.health_score(holdings, volatility_percent=15.0)
    assert 0 <= breakdown.overall_score <= 100


def test_analytics_raises_for_empty_portfolio():
    with pytest.raises(InsufficientDataError):
        AnalyticsEngine.sector_allocation([])


def test_rebalancing_suggests_buy_when_underweight():
    holdings = [_snapshot("AAPL", 10, 100, 100)]  # 1000 total value, 100% weight
    suggestions = RebalancingEngine.suggest(
        holdings, target_weights={"AAPL": 50.0, "MSFT": 50.0}, drift_tolerance_percent=2.0
    )
    by_symbol = {s.symbol: s for s in suggestions}
    assert by_symbol["MSFT"].action == "BUY"
    assert by_symbol["AAPL"].action == "SELL"


def test_rebalancing_holds_within_tolerance():
    holdings = [_snapshot("AAPL", 10, 100, 100)]
    suggestions = RebalancingEngine.suggest(
        holdings, target_weights={"AAPL": 99.0}, drift_tolerance_percent=5.0
    )
    assert suggestions[0].action == "HOLD"
