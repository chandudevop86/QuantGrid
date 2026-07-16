from app.institutional.collector import InstitutionalCollector
from app.institutional.models import InstitutionalMetrics


collector = InstitutionalCollector()



def save_metrics(db):

    market = collector.get_market_data()


    record = InstitutionalMetrics(

        fii_cash=0,
        dii_cash=0,

        fii_index_future=0,

        gift_nifty=
            market.get(
                "gift_nifty"
            ),

        india_vix=
            market.get(
                "india_vix"
            ),

        usdinr=
            market.get(
                "usdinr"
            ),

        crude_oil=
            market.get(
                "crude_oil"
            ),

        gold=
            market.get(
                "gold"
            )
    )


    db.add(record)
    db.commit()

    return record