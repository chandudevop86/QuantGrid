from __future__ import annotations

import logging

from fastapi import HTTPException, status

logger = logging.getLogger("quantgrid.upstream_errors")


def upstream_service_error(service: str, operation: str, exc: Exception) -> HTTPException:
    logger.warning(
        "upstream_service_request_failed",
        extra={"service": service, "operation": operation, "error_type": exc.__class__.__name__},
    )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "code": f"{service}_upstream_unavailable",
            "operation": operation,
            "message": f"The {service} request could not be completed. Retry or check service status.",
        },
    )
