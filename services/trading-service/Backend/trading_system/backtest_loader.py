from sqlalchemy import text
from Backend.database.connection import get_db


def load_nifty_candles(
    start_date: str,
    end_date: str,
    limit: int | None = None,
):

    db = next(get_db())

    query = """
    SELECT
        timestamp,
        open,
        high,
        low,
        close,
        volume
    FROM market_candles
    WHERE
        symbol = 'NIFTY'
        AND interval = '1'
        AND timestamp >= :start
        AND timestamp <= :end
    ORDER BY timestamp ASC
    """

    if limit:
        query += f" LIMIT {limit}"


    result = db.execute(
        text(query),
        {
            "start": start_date,
            "end": end_date,
        }
    )


    candles = []

    for row in result:

        candles.append(
            {
                "timestamp": row.timestamp,
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
        )


    return candles