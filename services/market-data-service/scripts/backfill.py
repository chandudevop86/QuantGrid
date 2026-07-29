from app.database.connection import SessionLocal
from app.services.backfill_service import BackfillService

db = SessionLocal()

BackfillService().backfill(
    db=db,
    symbol="NIFTY",
    security_id="13",
    exchange_segment="IDX_I",
    interval="1",
    days=365,
)

db.close()
