from __future__ import annotations

from datetime import date, timedelta

from app.modules.portfolio.domain.entities import CashFlow, PricePoint
from app.modules.portfolio.domain.exceptions import InsufficientDataError


class PerformanceEngine:
    """Pure, framework-agnostic engine for portfolio return calculations."""

    # ------------------------------------------------------------------ #
    # Simple time-window returns computed off a NAV / value history series
    # ------------------------------------------------------------------ #
    @staticmethod
    def _value_on_or_before(history: list[PricePoint], target: date) -> float | None:
        candidates = [p for p in history if p.as_of <= target]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.as_of).close_price

    @classmethod
    def _windowed_return(cls, history: list[PricePoint], as_of: date, lookback: timedelta) -> float:
        if len(history) < 2:
            raise InsufficientDataError("At least two NAV data points are required.")
        end_value = cls._value_on_or_before(history, as_of)
        start_value = cls._value_on_or_before(history, as_of - lookback)
        if end_value is None or start_value is None or start_value == 0:
            raise InsufficientDataError("Not enough historical NAV data for the requested window.")
        return ((end_value - start_value) / start_value) * 100.0

    @classmethod
    def daily_return(cls, history: list[PricePoint], as_of: date) -> float:
        sorted_hist = sorted(history, key=lambda p: p.as_of)
        prior = [p for p in sorted_hist if p.as_of < as_of]
        today = cls._value_on_or_before(sorted_hist, as_of)
        if not prior or today is None:
            raise InsufficientDataError("Not enough historical NAV data to compute daily return.")
        yesterday = prior[-1].close_price
        if yesterday == 0:
            raise InsufficientDataError("Prior NAV value is zero; cannot compute daily return.")
        return ((today - yesterday) / yesterday) * 100.0

    @classmethod
    def weekly_return(cls, history: list[PricePoint], as_of: date) -> float:
        return cls._windowed_return(history, as_of, timedelta(days=7))

    @classmethod
    def monthly_return(cls, history: list[PricePoint], as_of: date) -> float:
        return cls._windowed_return(history, as_of, timedelta(days=30))

    @classmethod
    def yearly_return(cls, history: list[PricePoint], as_of: date) -> float:
        return cls._windowed_return(history, as_of, timedelta(days=365))

    @classmethod
    def absolute_return(cls, history: list[PricePoint]) -> float:
        if len(history) < 2:
            raise InsufficientDataError("At least two NAV data points are required.")
        sorted_hist = sorted(history, key=lambda p: p.as_of)
        start_value = sorted_hist[0].close_price
        end_value = sorted_hist[-1].close_price
        if start_value == 0:
            raise InsufficientDataError("Starting NAV value is zero; cannot compute absolute return.")
        return ((end_value - start_value) / start_value) * 100.0

    @staticmethod
    def daily_return_series(history: list[PricePoint]) -> list[float]:
        """Returns a list of simple daily percentage returns, oldest-to-newest."""
        sorted_hist = sorted(history, key=lambda p: p.as_of)
        returns: list[float] = []
        for prev, curr in zip(sorted_hist, sorted_hist[1:]):
            if prev.close_price == 0:
                continue
            returns.append((curr.close_price - prev.close_price) / prev.close_price)
        return returns

    # ------------------------------------------------------------------ #
    # XIRR - money weighted return via Newton-Raphson with bisection fallback
    # ------------------------------------------------------------------ #
    @staticmethod
    def _xnpv(rate: float, cash_flows: list[CashFlow]) -> float:
        t0 = min(cf.when for cf in cash_flows)
        return sum(
            cf.amount / ((1.0 + rate) ** ((cf.when - t0).days / 365.0))
            for cf in cash_flows
        )

    @classmethod
    def _xnpv_derivative(cls, rate: float, cash_flows: list[CashFlow]) -> float:
        t0 = min(cf.when for cf in cash_flows)
        return sum(
            -((cf.when - t0).days / 365.0) * cf.amount
            / ((1.0 + rate) ** (((cf.when - t0).days / 365.0) + 1.0))
            for cf in cash_flows
        )

    @classmethod
    def xirr(cls, cash_flows: list[CashFlow], guess: float = 0.1) -> float:
        """
        Computes the annualized money-weighted rate of return (XIRR) for an
        arbitrary series of dated cash flows using Newton-Raphson, falling back
        to bisection if Newton fails to converge.

        Convention: outflows (investments/buys) are negative, inflows
        (sells/dividends, plus a terminal "current market value" flow) are positive.
        Returns a percentage (e.g. 12.34 for 12.34%).
        """
        if len(cash_flows) < 2:
            raise InsufficientDataError("XIRR requires at least two cash flows.")
        if not any(cf.amount < 0 for cf in cash_flows) or not any(cf.amount > 0 for cf in cash_flows):
            raise InsufficientDataError("XIRR requires both an outflow and an inflow.")

        rate = guess
        for _ in range(100):
            npv = cls._xnpv(rate, cash_flows)
            d_npv = cls._xnpv_derivative(rate, cash_flows)
            if d_npv == 0:
                break
            new_rate = rate - npv / d_npv
            if abs(new_rate - rate) < 1e-7:
                return new_rate * 100.0
            rate = new_rate
            if rate <= -0.999999:
                rate = -0.999999 + 1e-6

        # Bisection fallback over a wide, sane rate range.
        low, high = -0.999999, 10.0
        f_low, f_high = cls._xnpv(low, cash_flows), cls._xnpv(high, cash_flows)
        if f_low * f_high > 0:
            raise InsufficientDataError(
                "XIRR did not converge for the given cash flows (no sign change found)."
            )
        for _ in range(200):
            mid = (low + high) / 2.0
            f_mid = cls._xnpv(mid, cash_flows)
            if abs(f_mid) < 1e-6:
                return mid * 100.0
            if f_low * f_mid < 0:
                high = mid
            else:
                low, f_low = mid, f_mid
        return ((low + high) / 2.0) * 100.0
