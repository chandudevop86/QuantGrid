from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class BacktestAnalytics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    profit_factor: float
    average_rr: float
    expectancy: float
    max_drawdown: float
    average_holding_minutes: float


class TradeAnalytics:

    @staticmethod
    def calculate(trades: list[dict[str, Any]]) -> BacktestAnalytics:

        if not trades:
            return BacktestAnalytics(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                gross_profit=0.0,
                gross_loss=0.0,
                net_profit=0.0,
                profit_factor=0.0,
                average_rr=0.0,
                expectancy=0.0,
                max_drawdown=0.0,
                average_holding_minutes=0.0,
            )

        total = len(trades)

        winners = [
            t for t in trades
            if float(t.get("pnl", 0)) > 0
        ]

        losers = [
            t for t in trades
            if float(t.get("pnl", 0)) <= 0
        ]

        winning_count = len(winners)
        losing_count = len(losers)

        gross_profit = sum(
            float(t.get("pnl", 0))
            for t in winners
        )

        gross_loss = abs(
            sum(
                float(t.get("pnl", 0))
                for t in losers
            )
        )

        net_profit = gross_profit - gross_loss

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else 0.0
        )

        win_rate = (
            winning_count / total * 100
            if total > 0
            else 0.0
        )

        rr_values = [
            float(t.get("rr", 0))
            for t in trades
        ]

        average_rr = (
            sum(rr_values) / len(rr_values)
            if rr_values
            else 0.0
        )

        expectancy = net_profit / total

        max_drawdown = TradeAnalytics._max_drawdown(trades)

        avg_hold = TradeAnalytics._average_holding_time(trades)


        return BacktestAnalytics(
            total_trades=total,
            winning_trades=winning_count,
            losing_trades=losing_count,
            win_rate=round(win_rate, 2),
            gross_profit=round(gross_profit, 2),
            gross_loss=round(gross_loss, 2),
            net_profit=round(net_profit, 2),
            profit_factor=round(profit_factor, 2),
            average_rr=round(average_rr, 2),
            expectancy=round(expectancy, 2),
            max_drawdown=round(max_drawdown, 2),
            average_holding_minutes=round(avg_hold, 2),
        )


    @staticmethod
    def _max_drawdown(trades: list[dict[str, Any]]) -> float:

        balance = 0.0
        peak = 0.0
        max_dd = 0.0

        for trade in trades:

            balance += float(
                trade.get("pnl", 0)
            )

            peak = max(
                peak,
                balance
            )

            drawdown = peak - balance

            max_dd = max(
                max_dd,
                drawdown
            )

        return max_dd


    @staticmethod
    def _average_holding_time(
        trades: list[dict[str, Any]]
    ) -> float:

        durations = []

        for trade in trades:

            try:
                entry = datetime.fromisoformat(
                    trade["entry_time"]
                )

                exit_time = datetime.fromisoformat(
                    trade["exit_time"]
                )

                minutes = (
                    exit_time - entry
                ).total_seconds() / 60

                durations.append(minutes)

            except Exception:
                continue


        if not durations:
            return 0.0

        return sum(durations) / len(durations)