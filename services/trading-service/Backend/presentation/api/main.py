import os
import asyncio

from fastapi import FastAPI, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect

from Backend.core.config import validate_security_config
from Backend.core.database import SessionLocal
from Backend.application.job_store import init_job_store
from Backend.application.market_data_store import init_market_data_store
from Backend.application.paper_trade_store import init_paper_trade_store
from Backend.presentation.api.auth import init_auth_store, seed_bootstrap_users
from Backend.presentation.api.websocket_manager import manager


def _allowed_origins() -> list[str]:
    configured = os.getenv("CORS_ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]

    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://chandudevopai.shop:5173",
        "https://chandudevopai.shop:5173",
        "http://chandudevopai.shop",
        "https://chandudevopai.shop",
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
        validate_security_config()
        init_auth_store()
        with SessionLocal() as db:
            seed_bootstrap_users(db)
        init_job_store()
        init_market_data_store()
        init_paper_trade_store()
        manager.set_loop(asyncio.get_running_loop())

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics():
        try:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        except Exception:
            return Response("# prometheus_client is not installed\n", media_type="text/plain")
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)

        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    from Backend.presentation.api.dashboard_api import router as dashboard_router
    app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])

    # Auth
    from Backend.presentation.api.auth import admin_router, router as auth_router
    app.include_router(auth_router, prefix="/auth")
    app.include_router(admin_router)

    # Trading
    from Backend.presentation.api.trading_api import router as trading_router
    app.include_router(trading_router, prefix="/trading", tags=["Trading"])

    from Backend.presentation.api.production_api import router as production_router
    app.include_router(production_router)

    # Execution
    from Backend.presentation.api.execution import router as execution_router
    app.include_router(execution_router, prefix="/execution")

    from Backend.presentation.api.market_api import router as market_router
    app.include_router(market_router, prefix="/market")

    from Backend.presentation.api.broker_api import router as broker_router
    app.include_router(broker_router, prefix="/broker")

    from Backend.presentation.api.professional_api import router as professional_router
    app.include_router(professional_router)

    from Backend.presentation.api.notifications_api import router as notifications_router
    app.include_router(notifications_router)

    return app


app = create_app()
