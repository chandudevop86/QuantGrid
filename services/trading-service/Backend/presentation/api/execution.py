from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from Backend.domain.engine.execution_engine import ExecutionEngine
from Backend.domain.models.signal import StrategySignal
from Backend.presentation.api.market_api import get_price
from Backend.presentation.api.roles import require_roles

router = APIRouter()


# dependency injection (cleaner + testable)
def get_engine():
    return ExecutionEngine()


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
        "source": "signal_based",
        "order": jsonable_encoder(order),
    }
