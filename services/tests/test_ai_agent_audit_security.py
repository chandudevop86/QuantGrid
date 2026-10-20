from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE = ROOT / "services" / "ai-agent-service"


def _load_audit_security():
    module_path = AI_SERVICE / "audit_security.py"
    spec = importlib.util.spec_from_file_location("quantgrid_ai_audit_security", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_path_accepts_directory_inside_allowed_root(tmp_path):
    security = _load_audit_security()
    repo = tmp_path / "repo"
    repo.mkdir()

    resolved = security.resolve_audit_path("repo", allowed_root=tmp_path)

    assert resolved == repo.resolve()


def test_audit_path_rejects_outside_allowed_root(tmp_path):
    security = _load_audit_security()
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()

    with pytest.raises(security.AuditPathError, match="audit_path_outside_allowed_root"):
        security.resolve_audit_path(outside.as_posix(), allowed_root=allowed)


def test_audit_path_rejects_symlink_escape(tmp_path):
    security = _load_audit_security()
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    link = allowed / "escape"

    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")

    with pytest.raises(security.AuditPathError, match="audit_path_outside_allowed_root"):
        security.resolve_audit_path(link.as_posix(), allowed_root=allowed)


def test_ai_audit_endpoint_does_not_return_raw_exception_text():
    source = (AI_SERVICE / "app" / "main.py").read_text(encoding="utf-8")

    assert 'detail={"code": "audit_failed"}' in source
    assert "detail=str(e)" not in source
    assert "detail=str(exc)" not in source
    assert "resolve_audit_path(request.path)" in source
