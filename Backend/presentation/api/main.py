from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app.include_router(trading_router, prefix="/trading", tags=["Trading"])


def create_app():
    app = FastAPI(title="QuantGrid API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # lazy imports prevent partial failure
    from Backend.presentation.api.auth import router as auth_router
    app.include_router(auth_router, prefix="/auth")

    from Backend.presentation.api.trading_api import router as trading_router
    app.include_router(trading_router, prefix="/trading")

    from Backend.presentation.api.execution import router as execution_router
    app.include_router(execution_router, prefix="/execution")

    return app

app = create_app()