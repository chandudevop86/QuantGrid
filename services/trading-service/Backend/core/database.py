from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
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


def init_database() -> None:
    import Backend.domain.security.models  # noqa: F401
    import Backend.domain.trading_store_models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
