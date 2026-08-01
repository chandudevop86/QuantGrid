from __future__ import annotations

import math
import statistics

from app.modules.portfolio.domain.entities import PricePoint
from app.modules.portfolio.domain.exceptions import InsufficientDataError

TRADING_DAYS_PER_YEAR = 252


class RiskEngine:
    """Pure, framework-agnostic engine for portfolio risk metrics."""

    @staticmethod
    def _daily_returns(history: list[PricePoint]) -> list[float]:
        sorted_hist = sorted(history, key=lambda p: p.as_of)
        returns = []
        for prev, curr in zip(sorted_hist, sorted_hist[1:]):
            if prev.close_price:
                returns.append((curr.close_price - prev.close_price) / prev.close_price)
        return returns

    @classmethod
    def volatility(cls, history: list[PricePoint], annualize: bool = True) -> float:
        """Standard deviation of daily returns, expressed as a percentage."""
        returns = cls._daily_returns(history)
        if len(returns) < 2:
            raise InsufficientDataError("At least two return observations are required for volatility.")
        std_dev = statistics.pstdev(returns)
        if annualize:
            std_dev *= math.sqrt(TRADING_DAYS_PER_YEAR)
        return std_dev * 100.0

    @classmethod
    def sharpe_ratio(cls, history: list[PricePoint], risk_free_rate_annual: float = 0.06) -> float:
        returns = cls._daily_returns(history)
        if len(returns) < 2:
            raise InsufficientDataError("At least two return observations are required for Sharpe ratio.")
        daily_rf = (1 + risk_free_rate_annual) ** (1 / TRADING_DAYS_PER_YEAR) - 1
        excess_returns = [r - daily_rf for r in returns]
        mean_excess = statistics.fmean(excess_returns)
        std_dev = statistics.pstdev(returns)
        if std_dev == 0:
            raise InsufficientDataError("Return volatility is zero; Sharpe ratio is undefined.")
        return (mean_excess / std_dev) * math.sqrt(TRADING_DAYS_PER_YEAR)

    @classmethod
    def sortino_ratio(cls, history: list[PricePoint], risk_free_rate_annual: float = 0.06) -> float:
        returns = cls._daily_returns(history)
        if len(returns) < 2:
            raise InsufficientDataError("At least two return observations are required for Sortino ratio.")
        daily_rf = (1 + risk_free_rate_annual) ** (1 / TRADING_DAYS_PER_YEAR) - 1
        excess_returns = [r - daily_rf for r in returns]
        mean_excess = statistics.fmean(excess_returns)
        downside = [min(0.0, r) ** 2 for r in excess_returns]
        downside_deviation = math.sqrt(statistics.fmean(downside)) if downside else 0.0
        if downside_deviation == 0:
            raise InsufficientDataError("No downside deviation observed; Sortino ratio is undefined.")
        return (mean_excess / downside_deviation) * math.sqrt(TRADING_DAYS_PER_YEAR)

    @classmethod
    def max_drawdown(cls, history: list[PricePoint]) -> float:
        """Maximum peak-to-trough decline, expressed as a negative percentage."""
        sorted_hist = sorted(history, key=lambda p: p.as_of)
        if len(sorted_hist) < 2:
            raise InsufficientDataError("At least two NAV data points are required for max drawdown.")
        peak = sorted_hist[0].close_price
        max_dd = 0.0
        for point in sorted_hist:
            peak = max(peak, point.close_price)
            if peak > 0:
                drawdown = (point.close_price - peak) / peak
                max_dd = min(max_dd, drawdown)
        return max_dd * 100.0

    @classmethod
    def beta(cls, portfolio_history: list[PricePoint], benchmark_history: list[PricePoint]) -> float:
        p_returns = cls._daily_returns(portfolio_history)
        b_returns = cls._daily_returns(benchmark_history)
        n = min(len(p_returns), len(b_returns))
        if n < 2:
            raise InsufficientDataError("At least two aligned return observations are required for beta.")
        p_returns, b_returns = p_returns[-n:], b_returns[-n:]
        covariance = statistics.covariance(p_returns, b_returns)
        variance = statistics.pvariance(b_returns)
        if variance == 0:
            raise InsufficientDataError("Benchmark variance is zero; beta is undefined.")
        return covariance / variance

    @classmethod
    def alpha(cls, portfolio_history: list[PricePoint], benchmark_history: list[PricePoint],
              risk_free_rate_annual: float = 0.06) -> float:
        """Jensen's alpha, annualized, expressed as a percentage."""
        beta_value = cls.beta(portfolio_history, benchmark_history)
        p_returns = cls._daily_returns(portfolio_history)
        b_returns = cls._daily_returns(benchmark_history)
        n = min(len(p_returns), len(b_returns))
        p_returns, b_returns = p_returns[-n:], b_returns[-n:]

        annualized_portfolio_return = (
            (1 + statistics.fmean(p_returns)) ** TRADING_DAYS_PER_YEAR - 1
        )
        annualized_benchmark_return = (
            (1 + statistics.fmean(b_returns)) ** TRADING_DAYS_PER_YEAR - 1
        )
        expected_return = risk_free_rate_annual + beta_value * (
            annualized_benchmark_return - risk_free_rate_annual
        )
        return (annualized_portfolio_return - expected_return) * 100.0
