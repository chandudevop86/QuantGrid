from __future__ import annotations

import pytest


def test_weak_auth_secret_rejected(monkeypatch):
    from Backend.core import config

    monkeypatch.setattr(config, "ENV_FILE_LOADED", True)
    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "short")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        config.get_settings()


def test_sqlite_rejected_in_production(monkeypatch):
    from Backend.core import config

    monkeypatch.setattr(config, "ENV_FILE_LOADED", True)
    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "production-secret-that-is-long-enough-12345")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///prod.sqlite3")

    with pytest.raises(RuntimeError, match="SQLite is not allowed"):
        config.validate_security_config()


def test_live_trading_requires_separate_real_money_approval(monkeypatch):
    from Backend.core import config

    monkeypatch.setattr(config, "ENV_FILE_LOADED", True)
    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "production-secret-that-is-long-enough-12345")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")
    monkeypatch.setenv("QUANTGRID_ENABLE_LIVE_TRADING", "true")
    monkeypatch.delenv("QUANTGRID_LIVE_MONEY_APPROVED", raising=False)
    monkeypatch.setenv("BROKER_LIVE_ENABLED", "true")
    monkeypatch.setenv("QUANTGRID_BROKER_PROVIDER", "dhan")
    monkeypatch.setenv("QUANTGRID_BROKER_CLIENT_ID", "client")
    monkeypatch.setenv("QUANTGRID_BROKER_ACCESS_TOKEN", "token")
    monkeypatch.setenv("QUANTGRID_CAPITAL", "100000")
    monkeypatch.setenv("QUANTGRID_RISK_PER_TRADE_PCT", "1")
    monkeypatch.setenv("QUANTGRID_MAX_DAILY_LOSS", "3000")
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_PROVIDER", "dhan")
    config.reload_settings()

    with pytest.raises(RuntimeError, match="QUANTGRID_LIVE_MONEY_APPROVED"):
        config.validate_security_config(config.get_settings())
