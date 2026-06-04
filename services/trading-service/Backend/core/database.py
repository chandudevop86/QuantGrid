from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from Backend.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(database_url: str) -> dict:
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        return {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


def build_engine():
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, **_engine_kwargs(settings.database_url))


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _localhost_database_url(database_url: str) -> str | None:
    url = make_url(database_url)
    if (url.host or "").strip().lower() != "postgres":
        return None
    return url.set(host="127.0.0.1").render_as_string(hide_password=False)


def _is_unresolved_postgres_host_error(exc: OperationalError) -> bool:
    message = str(exc.orig).lower()
    return "failed to resolve host" in message and "'postgres'" in message


def _rebuild_engine(database_url: str) -> None:
    global engine
    engine.dispose()
    engine = create_engine(database_url, pool_pre_ping=True, **_engine_kwargs(database_url))
    SessionLocal.configure(bind=engine)


def init_database() -> None:
    import Backend.domain.security.models  # noqa: F401
    import Backend.domain.trading_store_models  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        settings = get_settings()
        fallback_url = _localhost_database_url(settings.database_url)
        if not fallback_url or not _is_unresolved_postgres_host_error(exc):
            raise
        _rebuild_engine(fallback_url)
        Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
