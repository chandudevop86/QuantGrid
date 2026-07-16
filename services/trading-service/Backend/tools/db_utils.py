from __future__ import annotations

import logging
import socket
import time
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from Backend.core.config import get_settings
from Backend.core.database import (
    SessionLocal,
    _is_unresolved_postgres_host_error,
    _localhost_database_url,
    _rebuild_engine,
    engine,
)

logger = logging.getLogger(__name__)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console = Console()
    RICH_AVAILABLE = True
except Exception:
    console = None
    RICH_AVAILABLE = False


# --------------------------------------------------------------------
# Console Helpers
# --------------------------------------------------------------------

def info(message: str) -> None:
    if RICH_AVAILABLE:
        console.print(f"[cyan]{message}[/cyan]")
    else:
        print(message)


def success(message: str) -> None:
    if RICH_AVAILABLE:
        console.print(f"[green]✓ {message}[/green]")
    else:
        print(f"[OK] {message}")


def warning(message: str) -> None:
    if RICH_AVAILABLE:
        console.print(f"[yellow]⚠ {message}[/yellow]")
    else:
        print(f"[WARNING] {message}")


def failure(message: str) -> None:
    if RICH_AVAILABLE:
        console.print(f"[red]✗ {message}[/red]")
    else:
        print(f"[ERROR] {message}")


# --------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------

def get_engine() -> Engine:
    """
    Returns working SQLAlchemy engine.

    If DATABASE_URL contains docker hostname 'postgres'
    and current machine cannot resolve it,
    automatically rebuild engine with localhost.
    """
    global engine

    try:
        with engine.connect():
            return engine

    except OperationalError as exc:

        settings = get_settings()

        fallback = _localhost_database_url(settings.database_url)

        if fallback and _is_unresolved_postgres_host_error(exc):
            logger.warning("Docker hostname unavailable. Falling back to localhost.")
            _rebuild_engine(fallback)

            from Backend.core.database import engine as rebuilt_engine

            return rebuilt_engine

        raise


# --------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------

@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


# --------------------------------------------------------------------
# Database URL
# --------------------------------------------------------------------

def mask_database_url(url: str) -> str:
    if "@" not in url:
        return url

    protocol, rest = url.split("://", 1)

    if ":" not in rest:
        return url

    userpass, host = rest.split("@", 1)

    if ":" not in userpass:
        return url

    username = userpass.split(":")[0]

    return f"{protocol}://{username}:***@{host}"


# --------------------------------------------------------------------
# Latency
# --------------------------------------------------------------------

def measure_latency(engine: Engine) -> float:

    start = time.perf_counter()

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    end = time.perf_counter()

    return round((end - start) * 1000, 2)


# --------------------------------------------------------------------
# Versions
# --------------------------------------------------------------------

def postgres_version(engine: Engine) -> str:

    with engine.connect() as conn:

        try:
            return conn.execute(text("SELECT version()")).scalar_one()

        except Exception:
            return "Unknown"


# --------------------------------------------------------------------
# Current User
# --------------------------------------------------------------------

def current_user(engine: Engine) -> str:

    with engine.connect() as conn:

        try:
            return conn.execute(text("SELECT current_user")).scalar_one()

        except Exception:
            return "Unknown"


# --------------------------------------------------------------------
# Database Name
# --------------------------------------------------------------------

def current_database(engine: Engine) -> str:

    with engine.connect() as conn:

        try:
            return conn.execute(text("SELECT current_database()")).scalar_one()

        except Exception:
            return "Unknown"


# --------------------------------------------------------------------
# Current Schema
# --------------------------------------------------------------------

def current_schema(engine: Engine) -> str:

    with engine.connect() as conn:

        try:
            return conn.execute(text("SELECT current_schema()")).scalar_one()

        except Exception:
            return "Unknown"


# --------------------------------------------------------------------
# Inspector
# --------------------------------------------------------------------

def get_inspector(engine: Engine):
    return inspect(engine)


# --------------------------------------------------------------------
# Table Exists
# --------------------------------------------------------------------

def table_exists(engine: Engine, table: str) -> bool:

    return table in inspect(engine).get_table_names()


# --------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------

def get_tables(engine: Engine) -> list[str]:

    return sorted(inspect(engine).get_table_names())


# --------------------------------------------------------------------
# Database Size
# --------------------------------------------------------------------

def database_size(engine: Engine) -> str:

    with engine.connect() as conn:

        try:
            return conn.execute(
                text(
                    """
                    SELECT pg_size_pretty(pg_database_size(current_database()))
                    """
                )
            ).scalar_one()

        except Exception:
            return "N/A"


# --------------------------------------------------------------------
# Table Size
# --------------------------------------------------------------------

def table_size(engine: Engine, table: str) -> str:

    with engine.connect() as conn:

        try:
            return conn.execute(
                text(
                    """
                    SELECT pg_size_pretty(pg_total_relation_size(:tbl))
                    """
                ),
                {"tbl": table},
            ).scalar_one()

        except Exception:
            return "N/A"


# --------------------------------------------------------------------
# Format Bytes
# --------------------------------------------------------------------

def format_bytes(size: int) -> str:

    power = 1024

    units = ["B", "KB", "MB", "GB", "TB"]

    n = 0

    while size >= power and n < len(units) - 1:
        size /= power
        n += 1

    return f"{size:.2f} {units[n]}"


# --------------------------------------------------------------------
# Pool Status
# --------------------------------------------------------------------

def pool_status(engine: Engine) -> str:

    try:
        return engine.pool.status()

    except Exception:
        return "Unavailable"


# --------------------------------------------------------------------
# Host Reachability
# --------------------------------------------------------------------

def can_resolve_host(host: str) -> bool:

    try:
        socket.gethostbyname(host)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------
# Rich Table
# --------------------------------------------------------------------

def create_table(title: str):

    if not RICH_AVAILABLE:
        return None

    table = Table(title=title)

    return table


# --------------------------------------------------------------------
# Rich Panel
# --------------------------------------------------------------------

def print_panel(title: str, body: str) -> None:

    if RICH_AVAILABLE:
        console.print(Panel.fit(body, title=title))
    else:
        print(f"\n=== {title} ===")
        print(body)