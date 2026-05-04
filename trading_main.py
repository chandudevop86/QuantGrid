from __future__ import annotations

from fastapi import FastAPI

from app.presentation.api.trading_api import router as trading_router


def create_app() -> FastAPI:
    app = FastAPI(title="Clean Trading System", version="1.0.0")
    app.include_router(trading_router)
    return app


app = create_app()
