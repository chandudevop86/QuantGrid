from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text

from Backend.core.config import get_settings, validate_security_config
from Backend.core.database import SessionLocal, engine, init_database


def _mask_database_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    if not parts.password:
        return database_url
    username = parts.username or ""
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{username}:***@{hostname}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def main() -> None:
    settings = validate_security_config()
    init_database()

    with SessionLocal() as db:
        db.execute(text("SELECT 1")).scalar_one()

    print("QuantGrid database connection OK")
    print(f"Environment: {settings.environment}")
    print(f"Database: {_mask_database_url(settings.database_url)}")
    print(f"Dialect: {engine.dialect.name}")


if __name__ == "__main__":
    main()
