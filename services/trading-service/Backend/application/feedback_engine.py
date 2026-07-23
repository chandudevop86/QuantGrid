from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class StrategyFeedback:

    strategy: str

    total_trades: int

    win_rate: float

    profit_factor: float

    average_pnl: float

    recommendation: str



class FeedbackEngine:


    def __init__(self, trade_repository):

        self.trade_repository = trade_repository



    # =====================================================
    # MAIN ANALYSIS
    # =====================================================

    def analyze_strategy(
        self,
        strategy: str
    ) -> StrategyFeedback:


        trades = self.trade_repository.get_trades(
            strategy
        )


        if not trades:

            return StrategyFeedback(

                strategy=strategy,

                total_trades=0,

                win_rate=0,

                profit_factor=0,

                average_pnl=0,

                recommendation="NO_DATA"
            )



        win_rate = self.calculate_win_rate(
            trades
        )


        profit_factor = self.calculate_profit_factor(
            trades
        )


        avg_pnl = self.calculate_average_pnl(
            trades
        )


        recommendation = self.generate_recommendation(

            win_rate,

            profit_factor,

            avg_pnl
        )



        return StrategyFeedback(

            strategy=strategy,

            total_trades=len(trades),

            win_rate=win_rate,

            profit_factor=profit_factor,

            average_pnl=avg_pnl,

            recommendation=recommendation
        )



    # =====================================================
    # METRICS
    # =====================================================


    def calculate_win_rate(
        self,
        trades: List[Any]
    ):


        wins = [

            t for t in trades
            if t.win

        ]


        return round(

            len(wins)
            /
            len(trades)
            *
            100,

            2

        )



    def calculate_profit_factor(
        self,
        trades
    ):


        profit = sum(

            t.pnl

            for t in trades

            if t.pnl > 0

        )


        loss = abs(sum(

            t.pnl

            for t in trades

            if t.pnl < 0

        ))



        if loss == 0:

            return profit



        return round(

            profit / loss,

            2

        )



    def calculate_average_pnl(
        self,
        trades
    ):


        return round(

            sum(
                t.pnl
                for t in trades
            )
            /
            len(trades),

            2

        )



    # =====================================================
    # AI FEEDBACK
    # =====================================================


    def generate_recommendation(
        self,
        win_rate,
        profit_factor,
        avg_pnl
    ):


        if (

            win_rate >= 55

            and profit_factor >= 1.5

            and avg_pnl > 0

        ):

            return "ENABLE"



        if (

            win_rate < 40

            or profit_factor < 1

        ):

            return "DISABLE"



        return "MONITOR"