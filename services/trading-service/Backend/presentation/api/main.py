from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app():
    app = FastAPI(title="QuantGrid API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth
    from Backend.presentation.api.auth import router as auth_router
    app.include_router(auth_router, prefix="/auth")

    # Trading
    from Backend.presentation.api.trading_api import router as trading_router
    app.include_router(trading_router, prefix="/trading", tags=["Trading"])

    # Execution
    from Backend.presentation.api.execution import router as execution_router
    app.include_router(execution_router, prefix="/execution")

    # Market (you missed this earlier!)
    from Backend.presentation.api.market_api import router as market_router
    app.include_router(market_router, prefix="/market")

    return app


app = create_app()