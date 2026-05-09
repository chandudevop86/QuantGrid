from fastapi import APIRouter

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/price")
def get_price():
    return {
        "symbol": "NIFTY",
        "price": 22450,
        "change": "+0.85%"
    }


@router.get("/signals")
def get_signals():
    return {
        "signal": "BUY",
        "confidence": 0.78
    }