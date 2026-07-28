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



def download_market_data():

    if not market_open():

        print(
            "Market closed - skipping download"
        )

        return


    db = SessionLocal()


    symbols = [

        (
            "NIFTY",
            settings.DHAN_SECURITY_ID_NIFTY
        ),

        (
            "BANKNIFTY",
            settings.DHAN_SECURITY_ID_BANKNIFTY
        ),

        (
            "FINNIFTY",
            settings.DHAN_SECURITY_ID_FINNIFTY
        )

    ]


    try:

        for symbol, security_id in symbols:

            result = market_downloader.download_symbol(

                db=db,

                symbol=symbol,

                security_id=security_id,

                exchange_segment=
                    settings.DHAN_EXCHANGE_SEGMENT_INDEX,

                interval="1"

            )


            print(
                "Market download:",
                result
            )


    except Exception as e:

        print(
            "Market download failed:",
            e
        )


    finally:

        db.close()



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