from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from presentation.api.trading_api import router as trading_router


def create_app() -> FastAPI:
    app = FastAPI(title="Clean Trading System", version="1.0.0")

    # ✅ ADD THIS (important for React)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # restrict later
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(trading_router)

    return app


app = create_app()