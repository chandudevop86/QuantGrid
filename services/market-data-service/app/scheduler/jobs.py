from apscheduler.schedulers.background import BackgroundScheduler

from app.database.connection import SessionLocal
from app.scheduler.downloader import market_downloader



scheduler = BackgroundScheduler()



def download_market_data():


    db = SessionLocal()


    try:

        # NIFTY example
        market_downloader.download_symbol(

            db,

            symbol="NIFTY",

            security_id="13",

            exchange_segment="IDX_I",

            interval="1"

        )


    except Exception as e:

        print(
            f"Market download failed: {e}"
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