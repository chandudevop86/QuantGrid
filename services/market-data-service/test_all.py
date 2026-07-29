from app.database.connection import SessionLocal
from app.scheduler.downloader import market_downloader
from app.config import settings

db = SessionLocal()

symbols = [
    ("NIFTY", settings.DHAN_SECURITY_ID_NIFTY),
    ("BANKNIFTY", settings.DHAN_SECURITY_ID_BANKNIFTY),
    ("FINNIFTY", settings.DHAN_SECURITY_ID_FINNIFTY),
]

for symbol, security_id in symbols:
    result = market_downloader.download_symbol(
        db=db,
        symbol=symbol,
        security_id=security_id,
        exchange_segment=settings.DHAN_EXCHANGE_SEGMENT_INDEX,
        interval="1",
    )
    print(result)

db.close()