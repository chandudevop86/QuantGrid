from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application settings, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_prefix="QUANTGRID_", env_file=".env", extra="ignore")

    app_name: str = "QuantGrid API"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"
    debug: bool = True

    database_url: str = "postgresql+asyncpg://quantgrid:quantgrid@localhost:5432/quantgrid"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_09f8b1c2e7"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    default_page_size: int = 20
    max_page_size: int = 200

    cors_allow_origins: list[str] = ["*"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
