from fastapi import APIRouter, Depends
from domain.services.execution_engine import ExecutionEngine
from domain.models.signal import StrategySignal

router = APIRouter()


# dependency injection (cleaner + testable)
def get_engine():
    return ExecutionEngine()


@router.post("/order")
async def place_order(
    signal: StrategySignal,
    engine: ExecutionEngine = Depends(get_engine)
):
    order = engine.order_from_signal(signal)

    # simulate execution layer hook
    # - broker API
    # - DB save
    # - queue system

    return {
        "status": "executed",
        "order": order.model_dump() if hasattr(order, "model_dump") else order.__dict__
    }