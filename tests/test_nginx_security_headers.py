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
        assert "connect-src 'self'" in content
        assert "wss:" in content
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


def test_production_nginx_rejects_unknown_hosts_and_avoids_host_header_redirects():
    https = (ROOT / "deploy/nginx/quantgrid.conf").read_text(encoding="utf-8")
    http = (ROOT / "deploy/nginx/quantgrid-http.conf").read_text(encoding="utf-8")
    for content in (https, http):
        assert "listen 80 default_server;" in content
        assert "server_name _;" in content
        assert "return 444;" in content
        assert "https://$host" not in content
        assert "return 301 https://chandudevopai.shop$request_uri;" in content
    assert "listen 443 ssl default_server;" in https
    assert "ssl_reject_handshake on;" in https


def test_production_nginx_has_rate_limits_tls_controls_and_cache_policy():
    content = (ROOT / "deploy/nginx/quantgrid.conf").read_text(encoding="utf-8")
    for expected in (
        "limit_req_zone $binary_remote_addr zone=quantgrid_api",
        "limit_req_zone $binary_remote_addr zone=quantgrid_auth",
        "limit_conn_zone $binary_remote_addr",
        "limit_req zone=quantgrid_auth",
        "limit_req zone=quantgrid_api",
        "limit_conn quantgrid_connection",
        "ssl_session_cache",
        "ssl_session_tickets off",
        "server_tokens off",
        'Cache-Control "public, max-age=31536000, immutable"',
        "log_format quantgrid_json",
        "$request_id",
        "proxy_set_header X-Request-ID $request_id",
    ):
        assert expected in content


def test_container_nginx_defines_upstream_timeouts_and_static_cache_policy():
    content = (ROOT / "docker/frontend-nginx.conf").read_text(encoding="utf-8")
    assert "server_tokens off;" in content
    assert "proxy_connect_timeout 5s;" in content
    assert "proxy_send_timeout 30s;" in content
    assert "proxy_read_timeout 60s;" in content
    assert "proxy_set_header X-Request-ID $request_id" in content
    assert 'Cache-Control "public, max-age=31536000, immutable"' in content


def test_nginx_installer_validates_and_renders_client_domain():
    installer = (ROOT / "deploy/scripts/nginx.sh").read_text(encoding="utf-8")
    legacy = (ROOT / "deploy/scripts/install_nginx.sh").read_text(encoding="utf-8")
    assert "validate_hostname" in installer
    assert "DOMAIN=" in installer
    assert "WWW_DOMAIN=" in installer
    assert "CERT_NAME=" in installer
    assert "mktemp" in installer
    assert "nginx -t" in installer
    assert "-L /etc/nginx/sites-enabled/default" in installer
    assert "sudo unlink /etc/nginx/sites-enabled/default" in installer
    assert 'exec bash "${SCRIPT_DIR}/nginx.sh" install' in legacy
