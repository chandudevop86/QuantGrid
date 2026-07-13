import os
import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect

from Backend.application.monitoring import observe_api_request
from Backend.application.redis_service import redis_service
from Backend.core.config import validate_security_config
from Backend.core.database import SessionLocal
from Backend.application.job_store import init_job_store
from Backend.application.market_data_store import init_market_data_store
from Backend.application.market_data_stream import start_market_data_stream, stop_market_data_stream
from Backend.application.order_store import init_order_store
from Backend.application.paper_trade_store import init_paper_trade_store
from Backend.application.position_store import init_position_store
from Backend.application.kill_switch import init_kill_switch_store
from Backend.application.investment_research_service import init_investment_research_store
from Backend.logging_config import configure_logging
from Backend.presentation.api.auth import init_auth_store, seed_bootstrap_users, verify_token
from Backend.domain.security.models import User
from Backend.presentation.api.metrics import prometheus_metrics_response
from Backend.presentation.api.websocket_manager import manager
from Backend.presentation.api.roles import require_roles


def _allowed_origins() -> list[str]:
    configured = os.getenv("CORS_ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]

    if os.getenv("QUANTGRID_ENV", "local").strip().lower() in {"prod", "production"}:
        raise RuntimeError("CORS_ALLOWED_ORIGINS must be explicitly configured in production.")

    vite_ports = range(5173, 5180)
    return [
        *(f"http://localhost:{port}" for port in vite_ports),
        *(f"http://127.0.0.1:{port}" for port in vite_ports),
        *(f"http://chandudevopai.shop:{port}" for port in vite_ports),
        *(f"https://chandudevopai.shop:{port}" for port in vite_ports),
        "http://chandudevopai.shop",
        "https://chandudevopai.shop",
    ]


def _allowed_origin_regex() -> str | None:
    if os.getenv("CORS_ALLOWED_ORIGINS"):
        return None
    if os.getenv("QUANTGRID_ENV", "local").strip().lower() in {"prod", "production"}:
        return None
    if os.getenv("QUANTGRID_ALLOW_PRIVATE_DEV_CORS", "").strip().lower() in {"1", "true", "yes"}:
        return r"^http://((localhost|127\.0\.0\.1)|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|192\.168\.\d+\.\d+):(517[3-9])$"
    return r"^http://(localhost|127\.0\.0\.1):(517[3-9])$"


def _allow_anonymous_websocket() -> bool:
    explicit = os.getenv("QUANTGRID_ALLOW_ANONYMOUS_WEBSOCKET")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes"}
    return False


async def _startup() -> None:
    validate_security_config()
    redis_service.configure()
    init_auth_store()
    with SessionLocal() as db:
        seed_bootstrap_users(db)
    init_job_store()
    init_market_data_store()
    init_order_store()
    init_paper_trade_store()
    init_position_store()
    init_kill_switch_store()
    init_investment_research_store()
    manager.set_loop(asyncio.get_running_loop())
    start_market_data_stream()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _startup()
    try:
        yield
    finally:
        await stop_market_data_stream()
        await manager.shutdown()


def create_app():
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    app = FastAPI(title="QuantGrid API", lifespan=lifespan)
    logger = logging.getLogger("quantgrid.api")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_origin_regex=_allowed_origin_regex(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        force_https = os.getenv("QUANTGRID_FORCE_HTTPS", "").strip().lower() in {"1", "true", "yes"}
        forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if force_https and forwarded_proto == "http":
            https_url = request.url.replace(scheme="https")
            return RedirectResponse(str(https_url), status_code=308)

        response = await call_next(request)
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started_at = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            logger.exception(
                "api_request_failed",
                extra={"request_id": request_id, "method": request.method, "path": request.url.path},
            )
            raise
        finally:
            latency = time.perf_counter() - started_at
            observe_api_request(request.method, request.url.path, status_code, latency)
            logger.info(
                "api_request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "latency_seconds": round(latency, 6),
                },
            )
            if "response" in locals():
                response.headers["X-Request-ID"] = request_id

    @app.get("/health")
    @app.get("/api/health")
    def health():
        from sqlalchemy import text

        from Backend.application.market_data_store import market_data_summary
        from Backend.domain.engine.strategy_engine import StrategyEngine

        db_status = {"healthy": True, "message": "Database query ok."}
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
        except Exception as exc:
            logger.warning("health_database_check_failed", exc_info=exc)
            db_status = {"healthy": False, "message": "Database unavailable."}

        redis_status = redis_service.status()

        strategies = StrategyEngine().available()
        market_store = market_data_summary("NIFTY", "1m")
        services = {
            "db": db_status,
            "redis": redis_status,
            "market_data": {
                "healthy": int(market_store.get("candles") or 0) > 0,
                "candles": market_store.get("candles"),
                "latest_timestamp": market_store.get("latest_candle_at"),
            },
            "strategy_engine": {
                "healthy": {"breakout", "mean_reversion", "supply_demand", "mtf", "btst", "cbt", "crt_tbs", "mtfa"}.issubset(set(strategies)),
                "registered": strategies,
            },
            "websocket": {
                "healthy": True,
                "connections": len(manager.active_connections),
                "broadcast_mode": redis_status.get("mode", "fallback"),
            },
        }
        return {"status": "ok" if all(item.get("healthy", False) for item in services.values()) else "degraded", "services": services}

    @app.get("/metrics")
    def metrics(_role: str = Depends(require_roles("admin", "ops"))):
        return prometheus_metrics_response()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        origin = websocket.headers.get("origin")
        if origin and origin not in _allowed_origins():
            logger.warning("websocket_rejected_origin", extra={"origin": origin})
            await websocket.close(code=4403, reason="Origin not allowed")
            return

        subprotocols = [item.strip() for item in websocket.headers.get("sec-websocket-protocol", "").split(",")]
        if len(subprotocols) != 2 or subprotocols[0] != "quantgrid" or not subprotocols[1]:
            if _allow_anonymous_websocket():
                if not await manager.connect(websocket):
                    return
                try:
                    while True:
                        try:
                            await asyncio.wait_for(websocket.receive_text(), timeout=5)
                        except asyncio.TimeoutError:
                            from Backend.presentation.api.dashboard_api import operations

                            payload = await run_in_threadpool(operations)
                            await websocket.send_json({"type": "dashboard_status", "payload": payload})
                except WebSocketDisconnect:
                    manager.disconnect(websocket)
                return
            logger.warning("websocket_rejected_missing_auth")
            await websocket.close(code=4401, reason="Authentication required")
            return
        token = subprotocols[1]
        try:
            claims = verify_token(token)
            with SessionLocal() as db:
                user = db.get(User, int(claims["uid"]))
                if user is None or user.role != claims.get("role"):
                    logger.warning("websocket_rejected_invalid_user")
                    await websocket.close(code=4401, reason="Invalid user")
                    return
        except Exception:
            logger.warning("websocket_rejected_invalid_token")
            await websocket.close(code=4401, reason="Invalid token")
            return

        if not await manager.connect(websocket, subprotocol="quantgrid"):
            return

        try:
            while True:
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=5)
                except asyncio.TimeoutError:
                    from Backend.presentation.api.dashboard_api import operations

                    payload = await run_in_threadpool(operations)
                    await websocket.send_json({"type": "dashboard_status", "payload": payload})
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    from Backend.presentation.api.dashboard_api import compatibility_router as dashboard_compatibility_router
    from Backend.presentation.api.dashboard_api import router as dashboard_router
    app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
    app.include_router(dashboard_compatibility_router, tags=["Dashboard"])

    from Backend.presentation.api.audit_api import router as audit_router
    app.include_router(audit_router)

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

    from Backend.presentation.api.orders_api import router as orders_router
    app.include_router(orders_router)

    from Backend.presentation.api.positions_api import router as positions_router
    app.include_router(positions_router)

    from Backend.presentation.api.risk_api import router as risk_router
    app.include_router(risk_router)

    from Backend.presentation.api.professional_api import router as professional_router
    app.include_router(professional_router)

    from Backend.presentation.api.notifications_api import router as notifications_router
    app.include_router(notifications_router)

    from Backend.presentation.api.modules_api import router as modules_router
    app.include_router(modules_router)

    from Backend.presentation.api.backtest_api import router as backtest_router
    app.include_router(backtest_router)

    from Backend.presentation.api.investing_api import router as investing_router
    app.include_router(investing_router)

    from Backend.presentation.api.institutional_api import router as institutional_router
    app.include_router(institutional_router)

    from Backend.presentation.api.data_quality_api import router as data_quality_router
    app.include_router(data_quality_router)

    from Backend.presentation.api.security_api import router as security_router
    app.include_router(security_router)

    return app


app = create_app()
