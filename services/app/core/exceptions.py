from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.modules.portfolio.domain.exceptions import PortfolioDomainError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PortfolioDomainError)
    async def _handle_domain_error(request: Request, exc: PortfolioDomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # exc.errors() can contain non-JSON-serializable objects (e.g. the
        # raised exception instance under ctx["error"] for custom/model
        # validators) - jsonable_encoder with a fallback coerces those to str.
        errors = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation failed.", "errors": errors},
        )
