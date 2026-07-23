from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, Optional
import uuid
import logging


logger = logging.getLogger(__name__)


# ============================================================
# INPUT MODEL
# ============================================================

@dataclass
class TradeAnalyticsInput:
    """
    Data received after successful order execution
    """

    decision: Any

    strategy: Any

    signal: Any

    score: Any

    risk: Any

    oms: Any

    broker: str

    market: Any



# ============================================================
# RESULT MODEL
# ============================================================

@dataclass
class TradeAnalyticsResult:
    """
    Final analytics record stored in DB
    """

    trade_id: str

    execution_time: datetime

    broker: str

    strategy: str

    signal_type: str

    ai_decision: str

    confidence: float

    signal_score: float

    risk_score: float


    entry_price: float

    exit_price: float

    quantity: int


    pnl: float

    pnl_pct: float


    slippage: float

    broker_latency_ms: float

    execution_time_ms: float


    win: bool


    analytics: Dict[str, Any] = field(
        default_factory=dict
    )



# ============================================================
# PNL OBJECT
# ============================================================

@dataclass
class PnLResult:

    amount: float

    percent: float



# ============================================================
# ANALYTICS SERVICE
# ============================================================

class TradeAnalyticsService:


    def __init__(self):

        self.trades = []



    # --------------------------------------------------------
    # MAIN ENTRY
    # --------------------------------------------------------

    def record(
        self,
        data: TradeAnalyticsInput
    ) -> TradeAnalyticsResult:


        pnl = self.calculate_pnl(
            data
        )


        result = TradeAnalyticsResult(

            trade_id=str(
                uuid.uuid4()
            ),


            execution_time=datetime.utcnow(),


            broker=data.broker,


            strategy=self.get_strategy(
                data.strategy
            ),


            signal_type=self.get_signal_type(
                data.signal
            ),


            ai_decision=self.get_decision(
                data.decision
            ),


            confidence=self.get_confidence(
                data.score
            ),


            signal_score=self.get_score(
                data.score
            ),


            risk_score=self.get_risk_score(
                data.risk
            ),



            entry_price=self.get_value(
                data.signal,
                "entry_price"
            ),


            exit_price=self.get_value(
                data.oms,
                "exit_price"
            ),


            quantity=self.get_value(
                data.signal,
                "quantity"
            ),



            pnl=pnl.amount,


            pnl_pct=pnl.percent,



            slippage=self.get_value(
                data.oms,
                "slippage"
            ),



            broker_latency_ms=self.get_value(
                data.oms,
                "latency_ms"
            ),



            execution_time_ms=self.get_value(
                data.oms,
                "execution_time_ms"
            ),



            win=pnl.amount > 0,



            analytics={

                "market_regime":
                    self.get_value(
                        data.market,
                        "regime"
                    ),


                "volatility":
                    self.get_value(
                        data.market,
                        "volatility"
                    ),


                "vix":
                    self.get_value(
                        data.market,
                        "vix"
                    ),


                "ai_reason":
                    self.get_value(
                        data.decision,
                        "reason"
                    ),


                "risk_allowed":
                    self.get_value(
                        data.risk,
                        "allowed"
                    )

            }

        )


        self.trades.append(
            result
        )


        logger.info(
            "Trade analytics recorded %s",
            result.trade_id
        )


        return result



    # --------------------------------------------------------
    # PNL CALCULATION
    # --------------------------------------------------------

    def calculate_pnl(
        self,
        data
    ) -> PnLResult:


        entry = self.get_value(
            data.signal,
            "entry_price"
        )


        exit_price = self.get_value(
            data.oms,
            "exit_price"
        )


        qty = self.get_value(
            data.signal,
            "quantity"
        )


        if not entry or not exit_price:

            return PnLResult(
                0,
                0
            )


        amount = (
            exit_price - entry
        ) * qty


        percent = (
            (exit_price-entry)
            /
            entry
        ) * 100



        return PnLResult(
            amount,
            round(percent,2)
        )



    # --------------------------------------------------------
    # SAFE OBJECT READERS
    # --------------------------------------------------------

    def get_value(
        self,
        obj,
        key,
        default=0
    ):

        if obj is None:
            return default


        if isinstance(obj,dict):

            return obj.get(
                key,
                default
            )


        return getattr(
            obj,
            key,
            default
        )



    def get_strategy(
        self,
        strategy
    ):

        if isinstance(strategy,str):

            return strategy


        return self.get_value(
            strategy,
            "name",
            "unknown"
        )



    def get_signal_type(
        self,
        signal
    ):

        return self.get_value(
            signal,
            "type",
            "unknown"
        )



    def get_decision(
        self,
        decision
    ):

        return self.get_value(
            decision,
            "action",
            "WAIT"
        )



    def get_confidence(
        self,
        score
    ):

        return float(
            self.get_value(
                score,
                "confidence",
                0
            )
        )



    def get_score(
        self,
        score
    ):

        return float(
            self.get_value(
                score,
                "total_score",
                0
            )
        )


    def get_risk_score(
        self,
        risk
    ):

        return float(
            self.get_value(
                risk,
                "score",
                0
            )
        )



    # --------------------------------------------------------
    # DASHBOARD SUPPORT
    # --------------------------------------------------------

    def get_all_trades(self):

        return [
            asdict(t)
            for t in self.trades
        ]



    def summary(self):

        total = len(
            self.trades
        )

        wins = len(
            [
                t for t in self.trades
                if t.win
            ]
        )


        pnl = sum(
            t.pnl
            for t in self.trades
        )


        return {

            "total_trades": total,

            "winning_trades": wins,

            "losing_trades":
                total - wins,

            "win_rate":
                round(
                    wins / total * 100,
                    2
                )
                if total else 0,


            "net_pnl":
                round(
                    pnl,
                    2
                )

        }