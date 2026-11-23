import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("postgres_archive", ROOT / "scripts/postgres_archive.py")
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


@pytest.mark.parametrize("driver", ["postgresql", "postgresql+psycopg", "postgresql+psycopg2"])
def test_backup_uses_libpq_scheme_and_password_only_in_environment(monkeypatch, driver):
    monkeypatch.setenv("DATABASE_URL", f"{driver}://archive_user:s%40fe%3Apass@127.0.0.1:5432/trading?sslmode=require")
    calls = []
    monkeypatch.setattr(archive.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)) or SimpleNamespace(returncode=0))
    assert archive.archive_command("backup", "/tmp/test.dump") == 0
    command, kwargs = calls[0]
    assert command[:4] == ["pg_dump", "--format=custom", "--no-owner", "--no-acl"]
    assert command[-1] == "postgresql://archive_user@127.0.0.1:5432/trading?sslmode=require"
    assert kwargs["env"]["PGPASSWORD"] == "s@fe:pass"
    assert all("s%40fe" not in argument and "s@fe" not in argument for argument in command)


def test_restore_uses_explicit_restore_target_and_propagates_failure(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod:password@prod/trading")
    monkeypatch.setenv("RESTORE_DATABASE_URL", "postgresql+psycopg://restore:other@localhost/recovery")
    calls = []
    monkeypatch.setattr(archive.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)) or SimpleNamespace(returncode=4))
    assert archive.archive_command("restore", "/tmp/test.dump") == 4
    command, kwargs = calls[0]
    assert "--exit-on-error" in command
    assert "--dbname=postgresql://restore@localhost/recovery" in command
    assert kwargs["env"]["PGPASSWORD"] == "other"


@pytest.mark.parametrize("url", ["sqlite:///db", "not-a-url-with-sensitive-value", "postgresql://localhost/db"])
def test_bad_configuration_fails_without_echoing_input(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(SystemExit) as error:
        archive.archive_command("backup", "/tmp/test.dump")
    assert str(error.value) == "Invalid PostgreSQL archive connection configuration"
    assert url not in str(error.value)
