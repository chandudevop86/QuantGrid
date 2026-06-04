from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text

from Backend.core import database
from Backend.core.config import get_settings, validate_security_config
from Backend.core.database import SessionLocal, init_database
from Backend.application.job_store import init_job_store
from Backend.application.kill_switch import init_kill_switch_store
from Backend.application.market_data_store import init_market_data_store
from Backend.application.order_store import init_order_store
from Backend.application.paper_trade_store import init_paper_trade_store
from Backend.application.position_store import init_position_store
from Backend.domain.security.audit import ensure_audit_schema


def _mask_database_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    if not parts.password:
        return database_url
    username = parts.username or ""
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{username}:***@{hostname}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def initialize_trading_database() -> None:
    init_database()
    init_job_store()
    init_market_data_store()
    init_paper_trade_store()
    init_position_store()
    init_order_store()
    init_kill_switch_store()
    with SessionLocal() as db:
        ensure_audit_schema(db)


def main() -> None:
    settings = validate_security_config()
    initialize_trading_database()

    with SessionLocal() as db:
        db.execute(text("SELECT 1")).scalar_one()

    print("QuantGrid database connection OK")
    print(f"Environment: {settings.environment}")
    print(f"Database: {_mask_database_url(settings.database_url)}")
    print(f"Dialect: {database.engine.dialect.name}")


if __name__ == "__main__":
    main()
