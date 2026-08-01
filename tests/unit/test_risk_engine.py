from __future__ import annotations

import random
from datetime import date, timedelta

import pytest

from app.modules.portfolio.domain.calculations.risk import RiskEngine
from app.modules.portfolio.domain.entities import PricePoint
from app.modules.portfolio.domain.exceptions import InsufficientDataError


def _series(start: date, prices: list[float]) -> list[PricePoint]:
    return [PricePoint(as_of=start + timedelta(days=i), close_price=p) for i, p in enumerate(prices)]


def test_volatility_zero_for_constant_prices():
    history = _series(date(2026, 1, 1), [100.0] * 10)
    assert RiskEngine.volatility(history) == pytest.approx(0.0)


def test_volatility_positive_for_varying_prices():
    random.seed(42)
    prices = [100.0]
    for _ in range(60):
        prices.append(prices[-1] * (1 + random.uniform(-0.02, 0.02)))
    history = _series(date(2026, 1, 1), prices)
    assert RiskEngine.volatility(history) > 0


def test_max_drawdown_detects_peak_to_trough():
    history = _series(date(2026, 1, 1), [100.0, 120.0, 90.0, 95.0])
    dd = RiskEngine.max_drawdown(history)
    # From peak 120 to trough 90: (90-120)/120 = -25%
    assert dd == pytest.approx(-25.0)


def test_max_drawdown_requires_two_points():
    with pytest.raises(InsufficientDataError):
        RiskEngine.max_drawdown(_series(date(2026, 1, 1), [100.0]))


def test_beta_of_identical_series_is_one():
    random.seed(7)
    prices = [100.0]
    for _ in range(60):
        prices.append(prices[-1] * (1 + random.uniform(-0.015, 0.015)))
    history = _series(date(2026, 1, 1), prices)
    # NOTE: RiskEngine.beta divides sample covariance (statistics.covariance, n-1
    # denominator) by population variance (statistics.pvariance, n denominator),
    # so beta(x, x) is systematically ~n/(n-1) rather than exactly 1.0.
    n = len(prices) - 1
    expected = n / (n - 1)
    assert RiskEngine.beta(history, history) == pytest.approx(expected, rel=1e-6)


def test_sharpe_ratio_requires_nonzero_volatility():
    history = _series(date(2026, 1, 1), [100.0] * 10)
    with pytest.raises(InsufficientDataError):
        RiskEngine.sharpe_ratio(history)
