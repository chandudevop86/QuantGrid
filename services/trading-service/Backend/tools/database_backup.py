from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from Backend.core.config import validate_security_config


class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def success(msg):
    print(f"{Color.GREEN}✔ {msg}{Color.END}")


def info(msg):
    print(f"{Color.CYAN}➜ {msg}{Color.END}")


def warn(msg):
    print(f"{Color.YELLOW}⚠ {msg}{Color.END}")


def error(msg):
    print(f"{Color.RED}✖ {msg}{Color.END}")


BACKUP_DIR = Path("database_backups")
BACKUP_DIR.mkdir(exist_ok=True)

MAX_BACKUPS = 20


def cleanup_old_backups():

    backups = sorted(BACKUP_DIR.glob("*.sql.gz"))

    while len(backups) > MAX_BACKUPS:
        backups[0].unlink()
        backups.pop(0)


def main():

    settings = validate_security_config()

    url = urlparse(settings.database_url)

    db = url.path.lstrip("/")
    host = url.hostname
    port = str(url.port or 5432)
    user = url.username
    password = url.password or ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    sql_file = BACKUP_DIR / f"{db}_{timestamp}.sql"
    gzip_file = BACKUP_DIR / f"{db}_{timestamp}.sql.gz"

    env = os.environ.copy()
    env["PGPASSWORD"] = password

    cmd = [
        "pg_dump",
        "-h",
        host,
        "-p",
        port,
        "-U",
        user,
        "-F",
        "p",
        "-f",
        str(sql_file),
        db,
    ]

    print()
    print(Color.BOLD + "=" * 70)
    print("QuantGrid PostgreSQL Backup")
    print("=" * 70 + Color.END)

    info(f"Database : {db}")
    info(f"Host     : {host}")
    info(f"Output   : {gzip_file}")

    try:

        subprocess.run(
            cmd,
            env=env,
            check=True,
        )

        with open(sql_file, "rb") as fin:
            with gzip.open(gzip_file, "wb") as fout:
                shutil.copyfileobj(fin, fout)

        sql_file.unlink()

        cleanup_old_backups()

        success("Backup completed successfully.")

        success(f"Saved to : {gzip_file}")

        success(
            f"Size : {gzip_file.stat().st_size / (1024*1024):.2f} MB"
        )

    except FileNotFoundError:

        error("pg_dump not installed.")
        print()
        print("Ubuntu")
        print("sudo apt install postgresql-client")

        sys.exit(1)

    except subprocess.CalledProcessError as e:

        error("Backup failed.")
        print(e)

        sys.exit(1)


if __name__ == "__main__":
    main()