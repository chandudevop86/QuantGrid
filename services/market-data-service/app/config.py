from pydantic_settings import BaseSettings



class Settings(BaseSettings):
    ...

    MARKET_SYMBOLS: str = "NIFTY"

    DHAN_SECURITY_ID_NIFTY: str = ""
    DHAN_SECURITY_ID_BANKNIFTY: str = ""
    DHAN_SECURITY_ID_FINNIFTY: str = ""
    DHAN_SECURITY_ID_MIDCPNIFTY: str = ""

    DHAN_EXCHANGE_SEGMENT_INDEX: str = "IDX_I"


settings = Settings()

class Settings(BaseSettings):

    SERVICE_NAME: str = "market-data-service"


    DATABASE_URL: str = (
        "postgresql+psycopg://quant:local-quantgrid-postgres@127.0.0.1:5432/quantgrid"
    )


    REDIS_URL: str = (
        "redis://localhost:6379/1"
    )


    # Dhan Credentials

    DHAN_CLIENT_ID: str = ""

    DHAN_ACCESS_TOKEN: str = ""


    # Dhan Market Symbols

    DHAN_SECURITY_ID_NIFTY: str = "13"

    DHAN_SECURITY_ID_BANKNIFTY: str = "25"

    DHAN_SECURITY_ID_FINNIFTY: str = "27"


    DHAN_EXCHANGE_SEGMENT_INDEX: str = "IDX_I"



    MARKET_PROVIDER: str = "dhan"


    TIMEFRAME: str = "1min"



    class Config:

        env_file = ".env"

        extra = "ignore"



settings = Settings()