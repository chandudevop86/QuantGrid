from app.database.connection import engine
from app.database.connection import Base

from app.models.candle import Candle



def create_tables():

    Base.metadata.create_all(
        bind=engine
    )