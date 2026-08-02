from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.modules.portfolio.domain.calculations.performance import PerformanceEngine
from app.modules.portfolio.domain.entities import CashFlow, PricePoint
from app.modules.portfolio.domain.exceptions import InsufficientDataError


def _series(start: date, prices: list[float]) -> list[PricePoint]:
    return [PricePoint(as_of=start + timedelta(days=i), close_price=p) for i, p in enumerate(prices)]


def test_absolute_return_simple():
    history = _series(date(2026, 1, 1), [100.0, 110.0, 121.0])
    assert PerformanceEngine.absolute_return(history) == pytest.approx(21.0)


def test_daily_return():
    history = _series(date(2026, 1, 1), [100.0, 105.0])
    result = PerformanceEngine.daily_return(history, date(2026, 1, 2))
    assert result == pytest.approx(5.0)


def test_daily_return_insufficient_data_raises():
    history = _series(date(2026, 1, 1), [100.0])
    with pytest.raises(InsufficientDataError):
        PerformanceEngine.daily_return(history, date(2026, 1, 1))


def test_weekly_and_monthly_return_windows():
    start = date(2026, 1, 1)
    prices = [100.0 + i for i in range(40)]
    history = _series(start, prices)
    as_of = start + timedelta(days=35)
    weekly = PerformanceEngine.weekly_return(history, as_of)
    monthly = PerformanceEngine.monthly_return(history, as_of)
    assert weekly > 0
    assert monthly > weekly  # longer window, monotonically increasing prices -> larger cumulative return


def test_xirr_simple_investment():
    # Invest 1000 today, worth 1100 exactly one year later -> ~10% XIRR
    today = date(2026, 1, 1)
    cash_flows = [
        CashFlow(when=today, amount=-1000.0),
        CashFlow(when=today + timedelta(days=365), amount=1100.0),
    ]
    result = PerformanceEngine.xirr(cash_flows)
    assert result == pytest.approx(10.0, abs=0.5)


def test_xirr_requires_inflow_and_outflow():
    today = date(2026, 1, 1)
    cash_flows = [
        CashFlow(when=today, amount=-1000.0),
        CashFlow(when=today + timedelta(days=30), amount=-500.0),
    ]
    with pytest.raises(InsufficientDataError):
        PerformanceEngine.xirr(cash_flows)


def test_xirr_multiple_cash_flows():
    today = date(2026, 1, 1)
    cash_flows = [
        CashFlow(when=today, amount=-1000.0),
        CashFlow(when=today + timedelta(days=180), amount=-500.0),
        CashFlow(when=today + timedelta(days=365), amount=1800.0),
    ]
    result = PerformanceEngine.xirr(cash_flows)
    assert isinstance(result, float)
