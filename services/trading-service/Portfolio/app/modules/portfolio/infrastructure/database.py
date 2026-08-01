from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from functools import lru_cache

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "QUANTGRID_DATABASE_URL",
    "postgresql+asyncpg://quantgrid:quantgrid@localhost:5432/quantgrid",
)
REDIS_URL = os.getenv("QUANTGRID_REDIS_URL", "redis://localhost:6379/0")


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """
    NOTE: If the host application already owns a shared SQLAlchemy engine
    (e.g. in `app.core.database`), prefer injecting that engine instead of
    creating a second connection pool. This factory exists so the Portfolio
    module can run standalone without editing existing project files.
    """
    return create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=get_engine(), expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a transactional AsyncSession."""
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@lru_cache(maxsize=1)
def get_redis_pool() -> redis.Redis:
    return redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)


async def get_redis_client() -> AsyncGenerator[redis.Redis, None]:
    """FastAPI dependency yielding a Redis client (used for caching market data)."""
    client = get_redis_pool()
    yield client
