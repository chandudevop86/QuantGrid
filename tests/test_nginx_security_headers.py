from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_all_frontend_nginx_configs_define_restrictive_csp():
    configs = [
        ROOT / "deploy" / "nginx" / "quantgrid.conf",
        ROOT / "docker" / "frontend-nginx.conf",
    ]

    for config in configs:
        content = config.read_text(encoding="utf-8")
        assert "Content-Security-Policy" in content
        assert "default-src 'self'" in content
        assert "object-src 'none'" in content
        assert "frame-ancestors 'none'" in content
        assert "script-src 'self'" in content
        assert "connect-src 'self' ws: wss:" in content
        assert "always;" in content


def test_nginx_csp_does_not_allow_unsafe_scripts_or_wildcard_sources():
    for relative_path in ("deploy/nginx/quantgrid.conf", "docker/frontend-nginx.conf"):
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        csp_line = next(line for line in content.splitlines() if "Content-Security-Policy" in line)
        assert "'unsafe-eval'" not in csp_line
        assert "script-src 'self' 'unsafe-inline'" not in csp_line
        assert "*" not in csp_line


def test_nginx_websocket_proxy_forwards_auth_subprotocol():
    for relative_path in ("deploy/nginx/quantgrid.conf", "docker/frontend-nginx.conf"):
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        ws_block = content.split("location /ws", 1)[1].split("location /", 1)[0]

        assert "proxy_http_version 1.1" in ws_block
        assert "proxy_set_header Upgrade $http_upgrade" in ws_block
        assert 'proxy_set_header Connection "upgrade"' in ws_block
        assert "proxy_set_header Sec-WebSocket-Protocol $http_sec_websocket_protocol" in ws_block


def test_api_responses_include_defense_in_depth_csp(app_client):
    response = app_client.get("/health")

    assert response.status_code == 200
    policy = response.headers["content-security-policy"]
    assert "default-src 'self'" in policy
    assert "object-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "script-src 'self'" in policy
    assert "'unsafe-eval'" not in policy
