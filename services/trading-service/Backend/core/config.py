from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class Settings:
    environment: str
    auth_secret: str
    database_url: str
    market_data_provider: str
    live_trading_enabled: bool
    broker_configured: bool
    allow_dev_seed_users: bool
    bootstrap_users: str | None

    @property
    def is_local(self) -> bool:
        return self.environment in {"local", "dev", "development", "test"}

    @property
    def is_production(self) -> bool:
        return self.environment in {"prod", "production"}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _default_sqlite_url() -> str:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    return f"sqlite:///{data_dir / 'quantgrid.sqlite3'}"


def get_settings() -> Settings:
    environment = os.getenv("QUANTGRID_ENV", "local").strip().lower()
    auth_secret = os.getenv("QUANTGRID_AUTH_SECRET")

    if not auth_secret:
        if environment == "local":
            auth_secret = secrets.token_urlsafe(48)
            logger.warning("QUANTGRID_AUTH_SECRET is missing; generated temporary local-only secret.")
        else:
            raise RuntimeError("QUANTGRID_AUTH_SECRET must be set outside local environment.")

    if len(auth_secret) < 32:
        raise RuntimeError("QUANTGRID_AUTH_SECRET must be at least 32 characters.")

    database_url = os.getenv("DATABASE_URL") or _default_sqlite_url()
    market_data_provider = os.getenv("QUANTGRID_MARKET_DATA_PROVIDER", "yahoo").strip().lower()
    live_trading_enabled = _truthy(os.getenv("QUANTGRID_ENABLE_LIVE_TRADING"))
    broker_configured = bool(
        os.getenv("QUANTGRID_BROKER_PROVIDER")
        and (os.getenv("QUANTGRID_BROKER_ACCESS_TOKEN") or os.getenv("QUANTGRID_BROKER_API_KEY"))
    )
    allow_dev_seed_users = environment == "local" and _truthy(os.getenv("QUANTGRID_ALLOW_DEV_SEED_USERS"))
    bootstrap_users = os.getenv("QUANTGRID_USERS")

    return Settings(
        environment=environment,
        auth_secret=auth_secret,
        database_url=database_url,
        market_data_provider=market_data_provider,
        live_trading_enabled=live_trading_enabled,
        broker_configured=broker_configured,
        allow_dev_seed_users=allow_dev_seed_users,
        bootstrap_users=bootstrap_users,
    )


def validate_bootstrap_users(settings: Settings) -> None:
    configured = settings.bootstrap_users or ""
    for item in configured.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 3:
            continue
        username, password, _role = parts
        normalized_username = username.lower()
        normalized_password = password.lower()
        weak_defaults = {
            normalized_username,
            f"{normalized_username}123",
            f"{normalized_username}@123",
            "password",
            "password123",
        }
        if normalized_password in weak_defaults:
            raise RuntimeError("Default credentials are not allowed in QUANTGRID_USERS.")


def validate_security_config(settings: Settings | None = None) -> Settings:
    settings = settings or get_settings()
    logger.info("QuantGrid environment mode: %s", settings.environment)

    if settings.is_production:
        if not os.getenv("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL must be set in production.")
        if settings.database_url.startswith("sqlite"):
            raise RuntimeError("SQLite is not allowed in production.")

    validate_bootstrap_users(settings)

    if settings.live_trading_enabled and not settings.broker_configured:
        raise RuntimeError("Live trading requires broker provider and credentials.")

    return settings
