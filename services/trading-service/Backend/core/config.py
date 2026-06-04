from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
ENV_FILE_LOADED = False
LOCAL_ENVIRONMENTS = {"local", "dev", "development", "test"}
CONTAINER_ONLY_DATABASE_HOSTS = {"postgres"}

@dataclass(frozen=True)
class Settings:
    environment: str
    auth_secret: str
    database_url: str
    market_data_provider: str
    allow_yahoo_for_live: bool
    broker_provider: str | None
    live_trading_enabled: bool
    broker_live_enabled: bool
    broker_configured: bool
    risk_engine_enabled: bool
    audit_logging_enabled: bool
    risk_configured: bool
    capital: float
    risk_per_trade_pct: float
    max_daily_loss: float
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


def _database_url_from_env(environment: str) -> str:
    database_url = os.getenv("DATABASE_URL") or ""
    if environment in LOCAL_ENVIRONMENTS and _uses_container_only_database_host(database_url):
        return _default_sqlite_url()
    return database_url or _default_sqlite_url()


def _uses_container_only_database_host(database_url: str) -> bool:
    if "://" not in database_url:
        return False
    try:
        from urllib.parse import urlsplit

        hostname = urlsplit(database_url).hostname
    except ValueError:
        return False
    return (hostname or "").strip().lower() in CONTAINER_ONLY_DATABASE_HOSTS


def _default_env_file() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: str | Path | None = None, *, override: bool = False) -> None:
    env_path = Path(path or os.getenv("QUANTGRID_ENV_FILE") or _default_env_file())
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if not key:
            continue
        if not override and key in os.environ:
            continue
        os.environ[key] = _strip_optional_quotes(value.strip())


def ensure_env_loaded() -> None:
    global ENV_FILE_LOADED
    if ENV_FILE_LOADED:
        return
    load_env_file()
    ENV_FILE_LOADED = True


def get_settings() -> Settings:
    ensure_env_loaded()
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

    database_url = _database_url_from_env(environment)
    market_data_provider = os.getenv("QUANTGRID_MARKET_DATA_PROVIDER", "yahoo").strip().lower()
    allow_yahoo_for_live = _truthy(os.getenv("QUANTGRID_ALLOW_YAHOO_LIVE") or os.getenv("QUANTGRID_ALLOW_YAHOO_FOR_LIVE"))
    broker_provider = (os.getenv("QUANTGRID_BROKER_PROVIDER") or "").strip().lower() or None
    live_trading_enabled = _truthy(os.getenv("QUANTGRID_ENABLE_LIVE_TRADING"))
    broker_live_enabled = _truthy(os.getenv("BROKER_LIVE_ENABLED"))
    risk_engine_enabled = not _truthy(os.getenv("RISK_ENGINE_DISABLED")) and os.getenv("RISK_ENGINE_ENABLED", "true").strip().lower() not in {"0", "false", "no"}
    audit_logging_enabled = os.getenv("AUDIT_LOGGING_ENABLED", "true").strip().lower() not in {"0", "false", "no"}
    broker_token = (
        os.getenv("QUANTGRID_BROKER_ACCESS_TOKEN")
        or os.getenv("DHAN_ACCESS_TOKEN")
        or os.getenv("ZERODHA_ACCESS_TOKEN")
    )
    broker_key = (
        os.getenv("QUANTGRID_BROKER_API_KEY")
        or os.getenv("QUANTGRID_BROKER_CLIENT_ID")
        or os.getenv("DHAN_CLIENT_ID")
        or os.getenv("ZERODHA_API_KEY")
    )
    broker_configured = bool(
        broker_provider
        and broker_token
        and (broker_provider == "dhan" or broker_key)
    )
    risk_env_keys = {
        "QUANTGRID_CAPITAL",
        "QUANTGRID_RISK_PER_TRADE_PCT",
        "QUANTGRID_MAX_DAILY_LOSS",
    }
    risk_configured = all(os.getenv(key) not in {None, ""} for key in risk_env_keys)
    capital = float(os.getenv("QUANTGRID_CAPITAL", "100000"))
    risk_per_trade_pct = float(os.getenv("QUANTGRID_RISK_PER_TRADE_PCT", "1"))
    max_daily_loss = float(os.getenv("QUANTGRID_MAX_DAILY_LOSS", "3000"))
    allow_dev_seed_users = environment == "local" and _truthy(os.getenv("QUANTGRID_ALLOW_DEV_SEED_USERS"))
    bootstrap_users = os.getenv("QUANTGRID_USERS")

    return Settings(
        environment=environment,
        auth_secret=auth_secret,
        database_url=database_url,
        market_data_provider=market_data_provider,
        allow_yahoo_for_live=allow_yahoo_for_live,
        broker_provider=broker_provider,
        live_trading_enabled=live_trading_enabled,
        broker_live_enabled=broker_live_enabled,
        broker_configured=broker_configured,
        risk_engine_enabled=risk_engine_enabled,
        audit_logging_enabled=audit_logging_enabled,
        risk_configured=risk_configured,
        capital=capital,
        risk_per_trade_pct=risk_per_trade_pct,
        max_daily_loss=max_daily_loss,
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
    if settings.live_trading_enabled and not settings.broker_live_enabled:
        raise RuntimeError("Live trading requires BROKER_LIVE_ENABLED=true.")
    if settings.live_trading_enabled and not settings.risk_configured:
        raise RuntimeError(
            "Live trading requires QUANTGRID_CAPITAL, QUANTGRID_RISK_PER_TRADE_PCT, and QUANTGRID_MAX_DAILY_LOSS."
        )
    if settings.live_trading_enabled and settings.market_data_provider == "yahoo" and not settings.allow_yahoo_for_live:
        raise RuntimeError("Live trading requires a trading-grade market data provider. Yahoo is paper/demo only.")

    return settings
