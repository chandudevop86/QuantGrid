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
