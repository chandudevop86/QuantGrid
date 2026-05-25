from __future__ import annotations

import os
import sys

ROOT_SECRET = "ci-production-secret-that-is-long-enough-12345"


def main() -> int:
    os.environ["QUANTGRID_ENV"] = "production"
    os.environ["QUANTGRID_AUTH_SECRET"] = ROOT_SECRET
    os.environ["DATABASE_URL"] = "sqlite:///should-not-pass.sqlite3"

    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "trading-service"))
    from Backend.core.config import get_settings, validate_security_config

    settings = get_settings()
    try:
        validate_security_config(settings)
    except RuntimeError as exc:
        if "SQLite is not allowed in production" in str(exc):
            print("Production SQLite guard is active.")
            return 0
        print(f"Unexpected production config error: {exc}")
        return 1
    print("Production SQLite was allowed; this must fail closed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
