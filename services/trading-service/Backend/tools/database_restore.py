from __future__ import annotations

import argparse
import gzip
import os
import shutil
import subprocess
import sys
import tempfile
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


def extract_sql(path: Path) -> Path:
    if path.suffix != ".gz":
        return path

    tmp = Path(tempfile.mktemp(suffix=".sql"))

    with gzip.open(path, "rb") as fin:
        with open(tmp, "wb") as fout:
            shutil.copyfileobj(fin, fout)

    return tmp


def restore_database(sql_file: Path):

    settings = validate_security_config()

    url = urlparse(settings.database_url)

    env = os.environ.copy()
    env["PGPASSWORD"] = url.password or ""

    db = url.path.lstrip("/")

    cmd = [
        "psql",
        "-h",
        url.hostname,
        "-p",
        str(url.port or 5432),
        "-U",
        url.username,
        "-d",
        db,
        "-f",
        str(sql_file),
    ]

    subprocess.run(cmd, env=env, check=True)


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("backup")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation",
    )

    args = parser.parse_args()

    backup = Path(args.backup)

    if not backup.exists():
        error(f"{backup} not found.")
        sys.exit(1)

    print()
    print(Color.BOLD + "=" * 70)
    print("QuantGrid Database Restore")
    print("=" * 70 + Color.END)

    info(f"Backup : {backup}")

    if not args.force:

        confirm = input(
            "\nThis will overwrite existing data.\nContinue? (yes/no): "
        )

        if confirm.lower() != "yes":
            warn("Restore cancelled.")
            return

    sql = extract_sql(backup)

    try:

        restore_database(sql)

        success("Database restored successfully.")

    except subprocess.CalledProcessError as e:

        error("Restore failed.")
        print(e)

    finally:

        if sql != backup and sql.exists():
            sql.unlink()


if __name__ == "__main__":
    main()
    