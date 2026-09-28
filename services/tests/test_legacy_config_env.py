from __future__ import annotations

import os
import sys


def _reset_legacy_config_modules() -> None:
    for name in list(sys.modules):
        if name == "Backend.config" or name.startswith("Backend.config."):
            del sys.modules[name]


def test_legacy_config_env_honors_quantgrid_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / "isolated.env"
    env_file.write_text("CORS_ALLOWED_ORIGINS=https://isolated.example\n", encoding="utf-8")

    monkeypatch.setenv("QUANTGRID_ENV_FILE", str(env_file))
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    _reset_legacy_config_modules()

    import Backend.config.env  # noqa: F401

    assert os.getenv("CORS_ALLOWED_ORIGINS") == "https://isolated.example"

    _reset_legacy_config_modules()
