from fastapi import APIRouter, Depends

from app.database import get_db
from app.institutional.service import save_metrics


router = APIRouter(
    prefix="/api/institutional",
    tags=["Institutional"]
)



@router.get("/")
def dashboard(
    db=Depends(get_db)
):

    data = save_metrics(db)


    return {

        "fii_cash":
            data.fii_cash,

        "dii_cash":
            data.dii_cash,


        "fii_index_future":
            data.fii_index_future,


        "gift_nifty":
            data.gift_nifty,


        "india_vix":
            data.india_vix,


        "usdinr":
            data.usdinr,


        "crude_oil":
            data.crude_oil,


        "gold":
            data.gold

    }