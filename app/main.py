from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.modules.portfolio.api.v1.router import router as portfolio_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing to warm up eagerly (engine/session-maker/redis pool are
    # all lazily created + cached on first use via lru_cache factories).
    yield
    # Shutdown: dispose the pooled DB engine and close the Redis connection pool.
    from app.modules.portfolio.infrastructure.database import get_engine, get_redis_pool

    await get_engine().dispose()
    await get_redis_pool().aclose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "QuantGrid API — Portfolio Management module: portfolios, holdings, "
            "transactions, performance, risk, analytics, watchlists, alerts, and "
            "rebalancing suggestions."
        ),
        version="1.0.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(portfolio_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        return {"status": "ok", "service": settings.app_name}

    return app


app = create_app()
