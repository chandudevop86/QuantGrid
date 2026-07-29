from argparse import ArgumentParser
from datetime import datetime

from app.database.connection import SessionLocal
from app.services.backfill_service import BackfillService
from app.config import settings


parser = ArgumentParser()

parser.add_argument("--symbol", required=True)
parser.add_argument("--from", dest="from_date", required=True)
parser.add_argument("--to", dest="to_date", required=True)

args = parser.parse_args()

security_map = {
    "NIFTY": settings.DHAN_SECURITY_ID_NIFTY,
    "BANKNIFTY": settings.DHAN_SECURITY_ID_BANKNIFTY,
    "FINNIFTY": settings.DHAN_SECURITY_ID_FINNIFTY,
}

db = SessionLocal()

try:
    start = datetime.strptime(
        args.from_date,
        "%Y-%m-%d",
    ).date()

    end = datetime.strptime(
        args.to_date,
        "%Y-%m-%d",
    ).date()

    days = (end - start).days

    BackfillService().backfill(
        db=db,
        symbol=args.symbol,
        security_id=security_map[args.symbol],
        exchange_segment=settings.DHAN_EXCHANGE_SEGMENT_INDEX,
        interval="1",
        days=days,
    )
finally:
    db.close()