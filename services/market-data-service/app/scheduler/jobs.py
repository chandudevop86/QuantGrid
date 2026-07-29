from apscheduler.schedulers.background import BackgroundScheduler

from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.database.connection import SessionLocal
from app.scheduler.downloader import market_downloader
from app.config import settings


scheduler = BackgroundScheduler(
    timezone="Asia/Kolkata"
)


def market_open():

    now = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).time()

    return (
        time(9, 15)
        <= now
        <= time(15, 30)
    )

cycle_start = datetime.now(ZoneInfo("Asia/Kolkata"))

print("=" * 60)
print(f"Download cycle started: {cycle_start}")

def download_market_data():

    if not market_open():

        print(
            "Market closed - skipping download"
        )

        return


    db = SessionLocal()


    symbols = {
            "NIFTY": settings.DHAN_SECURITY_ID_NIFTY,
            "BANKNIFTY": settings.DHAN_SECURITY_ID_BANKNIFTY,
            "FINNIFTY": settings.DHAN_SECURITY_ID_FINNIFTY,
            #"MIDCPNIFTY": settings.DHAN_SECURITY_ID_MIDCPNIFTY,
        }

    symbols = {
        symbol: security_id
        for symbol, security_id in symbols.items()
        if security_id
    }


    try:

        for symbol, security_id in symbols.items():

            result = market_downloader.download_symbol(

                db=db,

                symbol=symbol,

                security_id=security_id,

                exchange_segment=
                    settings.DHAN_EXCHANGE_SEGMENT_INDEX,

                interval="1"

            )

            print(
            f"{symbol}: "
            f"saved={result.get('saved')} "
            f"message={result.get('message', '')}"
        )

    except Exception as e:

        print("Market download failed:",e)

    finally:

        db.close()
    cycle_end = datetime.now(ZoneInfo("Asia/Kolkata"))

    print(f"Download cycle finished: {cycle_end}")
    print(f"Duration: {cycle_end - cycle_start}")
    print("=" * 60)


def start_scheduler():

    if scheduler.running:
        return


    scheduler.add_job(

        download_market_data,

        trigger="interval",

        minutes=1,

        id="market_data_download",

        replace_existing=True

    )


    scheduler.start()


    print(
        "Market data scheduler started"
    )