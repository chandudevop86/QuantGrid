from __future__ import annotations

import sys
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from Backend.core import database
from Backend.core.config import (
    get_settings,
    validate_security_config,
)
from Backend.core.database import (
    SessionLocal,
    init_database,
)

from Backend.application.job_store import init_job_store
from Backend.application.kill_switch import init_kill_switch_store
from Backend.application.market_data_store import init_market_data_store
from Backend.application.order_store import init_order_store
from Backend.application.paper_trade_store import init_paper_trade_store
from Backend.application.position_store import init_position_store

from Backend.domain.security.audit import ensure_audit_schema


# ==========================================================
# Terminal Colors
# ==========================================================

class Color:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


# ==========================================================
# Helpers
# ==========================================================

def success(msg: str):
    print(f"{Color.GREEN}✔ {msg}{Color.END}")


def info(msg: str):
    print(f"{Color.CYAN}➜ {msg}{Color.END}")


def warn(msg: str):
    print(f"{Color.YELLOW}⚠ {msg}{Color.END}")


def error(msg: str):
    print(f"{Color.RED}✖ {msg}{Color.END}")


# ==========================================================
# Mask Password
# ==========================================================

def mask_database_url(database_url: str) -> str:
    parts = urlsplit(database_url)

    if not parts.password:
        return database_url

    username = parts.username or ""
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""

    netloc = f"{username}:***@{hostname}{port}"

    return urlunsplit(
        (
            parts.scheme,
            netloc,
            parts.path,
            parts.query,
            parts.fragment,
        )
    )


# ==========================================================
# Initialize DB
# ==========================================================

def initialize_trading_database():

    init_database()

    init_job_store()
    init_market_data_store()
    init_paper_trade_store()
    init_position_store()
    init_order_store()
    init_kill_switch_store()

    with SessionLocal() as db:
        ensure_audit_schema(db)


# ==========================================================
# Main
# ==========================================================

def main():

    print()
    print(Color.BOLD + "=" * 70)
    print("          QuantGrid Database Health Check")
    print("=" * 70 + Color.END)

    settings = validate_security_config()

    initialize_trading_database()

    try:

        with SessionLocal() as db:

            db.execute(text("SELECT 1"))

            version = db.execute(
                text("SELECT version();")
            ).scalar()

            current_user = db.execute(
                text("SELECT current_user;")
            ).scalar()

            current_schema = db.execute(
                text("SELECT current_schema();")
            ).scalar()

        inspector = inspect(database.engine)

        tables = inspector.get_table_names()

        success("Database Connection Successful")

        print()

        info(f"Environment : {settings.environment}")
        info(f"Dialect     : {database.engine.dialect.name}")
        info(f"Database    : {mask_database_url(settings.database_url)}")
        info(f"Current User: {current_user}")
        info(f"Schema      : {current_schema}")

        print()

        info(f"Database Version")
        print(version)

        print()

        info(f"Tables Found : {len(tables)}")

        for table in sorted(tables):
            print(f"   • {table}")

        print()

        host = urlsplit(settings.database_url).hostname or ""

        if host == "postgres":
            warn("Running inside Docker/Compose (host = postgres)")
        elif host in ("127.0.0.1", "localhost"):
            success("Running on Local PostgreSQL")
        else:
            info(f"Database Host : {host}")

        print()
        success("Database Health Check PASSED")

    except SQLAlchemyError as e:

        error("Database Connection Failed")
        print(e)
        sys.exit(1)

    except Exception as e:

        error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()