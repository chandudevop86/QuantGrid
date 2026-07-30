from sqlalchemy import text

from Backend.core.database import get_db


def load_nifty_candles(
    start_date: str,
    end_date: str,
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

    result = db.execute(
        text(query),
        {
            "start": start_date,
            "end": end_date,
        },
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

    db.close()

    return candles