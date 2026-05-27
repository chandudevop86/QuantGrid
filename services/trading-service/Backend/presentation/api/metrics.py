from __future__ import annotations

from fastapi import Response


def prometheus_metrics_response() -> Response:
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    except Exception:
        body = (
            "# HELP quantgrid_prometheus_client_available Prometheus client availability.\n"
            "# TYPE quantgrid_prometheus_client_available gauge\n"
            "quantgrid_prometheus_client_available 0\n"
        )
        return Response(body, media_type="text/plain; version=0.0.4; charset=utf-8")

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
