from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from Backend.application.dto import serialize_signal
from Backend.application.trading_service import TradingService
from Backend.domain.models.signal import StrategySignal
from Backend.trading_system.backtesting import BacktestEngine
from Backend.trading_system.execution import ExecutionEngine
from Backend.trading_system.risk import GlobalRiskManager
from Backend.presentation.api.roles import require_roles, require_trade_execute


router = APIRouter(tags=["production-trading"])
service = TradingService()
risk_manager = GlobalRiskManager()
execution_engine = ExecutionEngine(risk_manager=risk_manager)


class SignalPayload(BaseModel):
    strategy_name: str = "AMD + FVG + Supply/Demand"
    symbol: str
    side: str
    entry_price: float
    stop_loss: float
    target_price: float
    signal_time: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_signal(self) -> StrategySignal:
        return StrategySignal(
            strategy_name=self.strategy_name,
            symbol=self.symbol,
            side=self.side.upper(),
            entry_price=self.entry_price,
            stop_loss=self.stop_loss,
            target_price=self.target_price,
            signal_time=self.signal_time,
            metadata=self.metadata,
        )


class StrategyRequest(BaseModel):
    strategy_name: str = Field(default="amd", examples=["amd"])
    symbol: str
    capital: float = 100_000
    risk_pct: float = 1.0
    rr_ratio: float = 2.0
    candles: list[dict[str, Any]]
    htf_candles: list[dict[str, Any]] | None = None
    mtf_candles: list[dict[str, Any]] | None = None
    daily_candles: list[dict[str, Any]] | None = None


class BacktestRequest(StrategyRequest):
    min_score: float = 10.0
    signals: list[SignalPayload] | None = None


class ExecuteTradeRequest(BaseModel):
    signal: SignalPayload
    market_price: float | None = None


@router.post("/generate-signal")
def generate_signal(
    payload: StrategyRequest,
    _role: str = Depends(require_roles("admin", "trader", "analyst")),
) -> list[dict[str, Any]]:
    signals = service.run_strategy(
        strategy_name=payload.strategy_name,
        data=payload.candles,
        symbol=payload.symbol,
        capital=payload.capital,
        risk_pct=payload.risk_pct,
        rr_ratio=payload.rr_ratio,
        params={
            key: value
            for key, value in {
                "htf_candles": payload.htf_candles,
                "mtf_candles": payload.mtf_candles,
                "daily_candles": payload.daily_candles,
            }.items()
            if value is not None
        },
    )
    return [serialize_signal(signal) for signal in signals]


@router.post("/backtest")
def backtest(
    payload: BacktestRequest,
    _role: str = Depends(require_roles("admin", "trader", "analyst")),
) -> dict[str, Any]:
    engine = BacktestEngine(risk_manager=GlobalRiskManager())
    return engine.run(
        candles=payload.candles,
        signals=[signal.to_signal() for signal in payload.signals] if payload.signals else None,
        strategy_name=payload.strategy_name,
        symbol=payload.symbol,
        capital=payload.capital,
        risk_pct=payload.risk_pct,
        rr_ratio=payload.rr_ratio,
        min_score=payload.min_score,
    ).to_dict()


@router.post("/execute-trade")
async def execute_trade(
    payload: ExecuteTradeRequest,
    _actor=Depends(require_trade_execute),
) -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Use /execution/order or /execution/auto-paper. Legacy production execution is disabled.",
    )


@router.get("/metrics")
def metrics(_role: str = Depends(require_roles("admin", "ops"))) -> dict[str, Any]:
    return asdict(risk_manager.snapshot())
