from __future__ import annotations

import os
from pathlib import Path


class AuditPathError(ValueError):
    """Raised when an audit target is invalid or outside the configured root."""


def configured_audit_root() -> Path:
    configured = os.getenv("QUANTGRID_AI_AUDIT_ROOT")
    root = Path(configured).expanduser() if configured else Path.cwd()
    return root.resolve()


def resolve_audit_path(raw_path: str, *, allowed_root: Path | None = None) -> Path:
    if not raw_path or not raw_path.strip():
        raise AuditPathError("audit_path_required")

    root = (allowed_root or configured_audit_root()).expanduser().resolve()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate

    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise AuditPathError("audit_path_unavailable") from exc

    if not resolved.is_dir():
        raise AuditPathError("audit_path_must_be_directory")

    if resolved != root and root not in resolved.parents:
        raise AuditPathError("audit_path_outside_allowed_root")

    return resolved
