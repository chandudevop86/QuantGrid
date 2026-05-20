import os

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.encoders import jsonable_encoder
from Backend.domain.engine.execution_engine import ExecutionEngine
from Backend.domain.models.signal import StrategySignal
from Backend.presentation.api.market_api import get_price
from Backend.presentation.api.roles import require_roles

router = APIRouter()


# dependency injection (cleaner + testable)
def get_engine():
    return ExecutionEngine()


def _execution_mode(x_quantgrid_mode: str = Header(default="paper", alias="X-QuantGrid-Mode")) -> str:
    mode = x_quantgrid_mode.strip().lower()
    if mode not in {"paper", "live"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid execution mode.")
    if mode == "live" and os.getenv("ENABLE_LIVE_TRADING", "false").strip().lower() not in {"1", "true", "yes"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Live trading is disabled. Set ENABLE_LIVE_TRADING=true and configure a broker before live execution.",
        )
    if mode == "live":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Live broker execution is not implemented for this endpoint.",
        )
    return mode


def _market_aligned(signal: StrategySignal) -> bool:
    price_response = get_price(signal.symbol)
    market_price = price_response.get("price")
    if market_price is None or float(market_price) <= 0:
        return False
    return abs(float(signal.entry_price) - float(market_price)) / float(market_price) <= 0.02


@router.post("/order")
async def place_order(
    signal: StrategySignal,
    engine: ExecutionEngine = Depends(get_engine),
    _role: str = Depends(require_roles("admin", "trader")),
    execution_mode: str = Depends(_execution_mode),
):
    if not _market_aligned(signal):
        return {
            "status": "no_trade",
            "reason": "Signal entry price is not aligned with market price.",
            "source": "signal_based",
        }

    order = engine.order_from_signal(signal)

    # simulate execution layer hook
    # - broker API
    # - DB save
    # - queue system

    return {
        "status": "paper_simulated",
        "execution_mode": execution_mode,
        "source": "signal_based",
        "order": jsonable_encoder(order),
    }
