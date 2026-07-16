from sqlalchemy import Column, Integer, Float, DateTime
from sqlalchemy.sql import func

from app.database import Base


class InstitutionalMetrics(Base):

    __tablename__ = "institutional_metrics"

    id = Column(Integer, primary_key=True)

    fii_cash = Column(Float)
    dii_cash = Column(Float)

    fii_index_future = Column(Float)

    gift_nifty = Column(Float)
    india_vix = Column(Float)

    usdinr = Column(Float)

    crude_oil = Column(Float)
    gold = Column(Float)

    created_at = Column(
        DateTime,
        server_default=func.now()
    )