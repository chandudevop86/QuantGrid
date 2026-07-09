from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.analysis.volume_analysis import analyze_volume
from app.models.volume_models import VolumeAnalysisRequest, VolumeAnalysisResponse


router = APIRouter(prefix="/market", tags=["market"])


@router.post("/volume-analysis", response_model=VolumeAnalysisResponse)
def post_volume_analysis(payload: VolumeAnalysisRequest) -> dict:
    if not payload.candles:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="candles must not be empty.")
    return analyze_volume(
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        candles=payload.candles,
        delivery_data=payload.delivery_data,
    ).to_dict()
