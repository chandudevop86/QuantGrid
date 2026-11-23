"""Run PostgreSQL archive tools with application URL drivers normalized.

Passwords go through the child environment, never command arguments or logs.
"""
from __future__ import annotations

import argparse
import os
import subprocess

from sqlalchemy.engine import URL, make_url


def archive_command(action: str, archive: str) -> int:
    variable = "DATABASE_URL" if action == "backup" else "RESTORE_DATABASE_URL"
    try:
        url = make_url(os.environ.get(variable, ""))
        if url.get_backend_name() not in {"postgres", "postgresql"} or not url.username or not url.database:
            raise ValueError("PostgreSQL required")
        environment = os.environ.copy()
        if url.password is not None:
            environment["PGPASSWORD"] = url.password
        # libpq accepts postgresql://, not SQLAlchemy's postgresql+driver://.
        connection = URL.create("postgresql", username=url.username, host=url.host, port=url.port,
                                database=url.database, query=url.query).render_as_string(hide_password=False)
    except Exception:
        # Parser exceptions can embed the original URL; never echo them.
        raise SystemExit("Invalid PostgreSQL archive connection configuration") from None
    if action == "backup":
        command = ["pg_dump", "--format=custom", "--no-owner", "--no-acl", f"--file={archive}", connection]
    else:
        command = ["pg_restore", "--exit-on-error", "--no-owner", "--no-acl", "--clean", "--if-exists",
                   f"--dbname={connection}", archive]
    return subprocess.run(command, env=environment, check=False).returncode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("archive")
    args = parser.parse_args()
    raise SystemExit(archive_command(args.action, args.archive))


if __name__ == "__main__":
    main()
