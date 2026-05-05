from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from presentation.api.auth import router as auth_router
from presentation.api.trading import router as trading_router
from presentation.api.execution import router as execution_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="QuantGrid API",
        version="1.0.0"
    )

    # --------------------
    # CORS (React frontend)
    # --------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --------------------
    # ROUTERS (modular APIs)
    # --------------------
    app.include_router(auth_router, prefix="/auth", tags=["Auth"])
    app.include_router(trading_router, prefix="/trading", tags=["Trading"])
    app.include_router(execution_router, prefix="/execution", tags=["Execution"])

    return app


app = create_app()