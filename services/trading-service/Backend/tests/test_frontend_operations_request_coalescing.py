from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_operations_api_coalesces_requests_with_auth_aware_short_cache():
    source = (ROOT / "apps" / "frontend" / "src" / "api" / "index.ts").read_text(encoding="utf-8")

    assert "OPERATIONS_CACHE_TTL_MS = 3000" in source
    assert "getAuthToken()" in source
    assert "operationsCache?.authKey === authKey" in source
    assert "operationsRequest?.authKey === authKey" in source
    assert "operationsRequest = { authKey, promise }" in source
    assert "operationsStatus," in source


def test_operations_api_does_not_cache_failed_requests():
    source = (ROOT / "apps" / "frontend" / "src" / "api" / "index.ts").read_text(encoding="utf-8")
    status_function = source.split("function operationsStatus()", 1)[1].split("export type SignalPayload", 1)[0]

    assert ".then((data) =>" in status_function
    assert "operationsCache =" in status_function
    assert ".finally(() =>" in status_function
    assert "operationsRequest = null" in status_function


def test_operations_compatibility_route_is_used_only_when_canonical_route_is_missing():
    source = (ROOT / "apps" / "frontend" / "src" / "api" / "index.ts").read_text(encoding="utf-8")
    status_function = source.split("function operationsStatus()", 1)[1].split("export type SignalPayload", 1)[0]

    assert "status === 404 || status === 405" in source
    assert "if (!canonicalRouteUnavailable(error)) throw error" in status_function
    assert 'API.get("/operations/status")' in status_function
