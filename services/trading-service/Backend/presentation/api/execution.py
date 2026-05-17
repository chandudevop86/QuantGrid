from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from Backend.domain.engine.execution_engine import ExecutionEngine
from Backend.domain.models.signal import StrategySignal
from Backend.presentation.api.roles import require_roles

router = APIRouter()


# dependency injection (cleaner + testable)
def get_engine():
    return ExecutionEngine()


@router.post("/order")
async def place_order(
    signal: StrategySignal,
    engine: ExecutionEngine = Depends(get_engine),
    _role: str = Depends(require_roles("admin", "trader")),
):
    order = engine.order_from_signal(signal)

    # simulate execution layer hook
    # - broker API
    # - DB save
    # - queue system

    return {
        "status": "paper_simulated",
        "order": jsonable_encoder(order),
    }
