from apscheduler.schedulers.background import BackgroundScheduler

from app.database.connection import SessionLocal

from app.scheduler.downloader import market_downloader

from app.config import settings



scheduler = BackgroundScheduler()



def download_market_data():


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

                db,

                symbol=symbol,

                security_id=security_id,

                exchange_segment=settings.DHAN_EXCHANGE_SEGMENT_INDEX,

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


    scheduler.add_job(

        download_market_data,

        "interval",

        minutes=1,

        id="market_data_download",

        replace_existing=True

    )


    scheduler.start()