from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    SERVICE_NAME: str = "market-data-service"

    DATABASE_URL: str = (
        "postgresql://postgres:postgres@localhost:5432/quantgrid"
    )

    REDIS_URL: str = (
        "redis://localhost:6379/1"
    )

    DHAN_CLIENT_ID: str = ""
    DHAN_ACCESS_TOKEN: str = ""

    MARKET_PROVIDER: str = "dhan"

    TIMEFRAME: str = "1min"


    class Config:
        env_file = ".env"


settings = Settings()