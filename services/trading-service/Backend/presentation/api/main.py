import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from Backend.application.job_store import init_job_store


def _allowed_origins() -> list[str]:
    configured = os.getenv("CORS_ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]

    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://chandudevopai.shop:5173",
        "https://chandudevopai.shop:5173",
        "https://chandudevopai.shop",
        "http://13.222.179.171:5173",
    ]


def create_app():
    app = FastAPI(title="QuantGrid API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def startup():
        init_job_store()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    from Backend.presentation.api.dashboard_api import router as dashboard_router
    app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])

    # Auth
    from Backend.presentation.api.auth import router as auth_router
    app.include_router(auth_router, prefix="/auth")

    # Trading
    from Backend.presentation.api.trading_api import router as trading_router
    app.include_router(trading_router, prefix="/trading", tags=["Trading"])

    # Execution
    from Backend.presentation.api.execution import router as execution_router
    app.include_router(execution_router, prefix="/execution")

    from Backend.presentation.api.market_api import router as market_router
    app.include_router(market_router, prefix="/market")

    return app


app = create_app()
