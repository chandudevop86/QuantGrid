from Backend.application.decision_pipeline import DecisionPipelineService
from Backend.application.signal_scoring_engine import SignalScoringEngine, SignalScoringInput

from Backend.application.risk_engine import RiskEngine
from Backend.application.trading_service import TradingService
from Backend.application.order_management import OrderManagementService
from Backend.application.trade_analytics_engine import TradeAnalyticsService
from Backend.application.feedback_engine import FeedbackEngine
from Backend.application.strategy_selection_engine import (
    StrategySelector,
    StrategySelectionInput
)
from Backend.infrastructure.broker.broker_client import broker_client_for_mode
from Backend.infrastructure.repositories.order_repository import OrderRepository


class TradingOrchestrator:

    def __init__(self,trade_repository):
        self.pipeline = DecisionPipelineService()
        self.trade_repository = trade_repository
        self.scoring = SignalScoringEngine()
        self.selector = StrategySelector()
        self.risk = RiskEngine()
        self.trading_service = TradingService()
        self.oms = OrderManagementService(
            broker=broker_client_for_mode("paper"),
            order_repository=OrderRepository(),
        )
        self.analytics = TradeAnalyticsService()
        self.feedback = FeedbackEngine(trade_repository=self.trade_repository)

    def execute_cycle(self, market):

        # 1. AI Decision
        decision = self.pipeline.run(
            market,
            risk_blocked=False
        )

        # 2. Select strategy
        strategy_input = StrategySelectionInput(

            trend=market.trend or "Unknown",

            market_regime=getattr(
                market,
                "market_regime",
                "Unknown"
            ),

            volatility=getattr(
                market,
                "volatility",
                "Normal"
            ),

            volume=getattr(
                market,
                "volume",
                "Normal"
            ),

            oi_bias=market.oi_bias or "Neutral",

            vwap_relation=market.vwap_relation or "Unknown",

            confidence=getattr(
                decision,
                "confidence",
                50
            ),

            risk_reward=2.0,

            liquidity=getattr(
                market,
                "liquidity",
                "Normal"
            ),

            expiry_day=market.expiry_day,

            news_driven=getattr(
                market,
                "news",
                False
            )
        )


        strategy_result = self.selector.select(
            strategy_input
        )


        strategy = strategy_result.strategy_name


        # 3. Generate trading signal
        signals = self.trading_service.run_strategy(
            strategy_name=strategy,
            data=market.candles,
            symbol=market.symbol,
            capital=market.capital,
            risk_pct=(
                market.risk_per_trade / market.capital
                if market.capital
                else 0.01
            ),
            params={
                "market": market
            }
        )

        if not signals:
                print(
                        f"No signals generated for strategy={strategy}"
                )
                return None
                

        signal = signals[0]
        print(
                "Generated Signal:",
                            signal
                )

        # 4. Score signal
        score = self.scoring.score(
            SignalScoringInput(
                signal=signal,
                market=market,
                decision=decision,
                strategy_name=strategy
            )
        )


                # 5. Risk validation

        context = {
            "strategy": strategy,

            "capital": market.capital,
            "capital_per_trade": getattr(signal, "entry_price", 0),

            "daily_pnl": getattr(market, "daily_pnl", 0),
            "trades_today": getattr(market, "trades_today", 0),
            "open_positions": getattr(market, "open_positions", 0),
            "consecutive_losses": getattr(market, "consecutive_losses", 0),

            "broker_connected": True,
            "broker_circuit_active": False,

            "expiry_day": getattr(market, "expiry_day", False),
            "market_data_age_seconds": getattr(
                market,
                "market_data_age_seconds",
                0,
            ),
            "vix": getattr(market, "vix", 0),
            "gap_pct": getattr(market, "gap_pct", 0),
            "gamma": getattr(market, "gamma", 0),

            "bid_price": getattr(market, "bid_price", 0),
            "ask_price": getattr(market, "ask_price", 0),
            "slippage_bps": getattr(market, "slippage_bps", 0),

            "portfolio_exposure_pct": getattr(
                market,
                "portfolio_exposure_pct",
                0,
            ),
            "symbol_exposure_pct": getattr(
                market,
                "symbol_exposure_pct",
                0,
            ),
            "correlated_positions": getattr(
                market,
                "correlated_positions",
                0,
            ),

            "news": getattr(market, "news", False),

            "active_trade_keys": [],
        }

        approval = self.risk.validate(
            signal,
            context,
        )

        if not approval.allowed:
            print("Risk rejected:", approval)
            return approval
        context["prevalidated_risk"] = approval

        # 6. Create trade

        import asyncio

        order = asyncio.run(
            self.oms.submit_signal(
                signal=signal,
                context=context,
            )
        )

        # 8. Analytics
        self.analytics.record(
            order
        )



        # 9. Feedback
        self.feedback.update(
            order
        )

        print(
                "Order Created:",
                order
        )
        return order