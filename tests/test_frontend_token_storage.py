from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_uses_tab_scoped_storage_for_auth_token():
    roles = (ROOT / "apps/frontend/src/roles.ts").read_text(encoding="utf-8")
    client = (ROOT / "apps/frontend/src/api/client.ts").read_text(encoding="utf-8")
    socket = (ROOT / "apps/frontend/src/socket.ts").read_text(encoding="utf-8")

    assert 'sessionStorage.setItem("quantgrid_token", token)' in roles
    assert 'sessionStorage.removeItem("quantgrid_token")' in roles
    assert 'localStorage.removeItem("quantgrid_token")' in roles
    assert 'localStorage.setItem("quantgrid_token", token)' not in roles
    assert "getAuthToken()" in client
    assert "getAuthToken()" in socket
    assert 'new WebSocket(target.toString(), ["quantgrid", token])' in socket
    assert "?token=" not in socket


def test_legacy_persistent_token_is_migrated_and_deleted():
    roles = (ROOT / "apps/frontend/src/roles.ts").read_text(encoding="utf-8")
    helper = roles.split("export function getAuthToken()", 1)[1].split("function decodeAuthClaims", 1)[0]

    assert 'localStorage.getItem("quantgrid_token")' in helper
    assert 'sessionStorage.setItem("quantgrid_token", legacyToken)' in helper
    assert 'localStorage.removeItem("quantgrid_token")' in helper
