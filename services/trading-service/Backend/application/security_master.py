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


def success(msg: str) -> None:
    print(f"{Color.GREEN}✔ {msg}{Color.END}")


def info(msg: str) -> None:
    print(f"{Color.CYAN}➜ {msg}{Color.END}")


def warn(msg: str) -> None:
    print(f"{Color.YELLOW}⚠ {msg}{Color.END}")


def error(msg: str) -> None:
    print(f"{Color.RED}✖ {msg}{Color.END}")


def extract_sql(path: Path) -> Path:
    if path.suffix != ".gz":
        return path

    # Secures the filename allocation atomically to satisfy Bandit (B306)
    with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp_file:
        tmp = Path(tmp_file.name)

    with gzip.open(path, "rb") as fin:
        with open(tmp, "wb") as fout:
            shutil.copyfileobj(fin, fout)

    return tmp


def restore_database(sql_file: Path) -> None:
    settings = validate_security_config()
    url = urlparse(settings.database_url)

    env = os.environ.copy()
    env["PGPASSWORD"] = url.password or ""

    db = url.path.lstrip("/")

    cmd = [
        "psql",
        "-h",
        url.hostname or "localhost",
        "-p",
        str(url.port or 5432),
        "-U",
        url.username or "postgres",
        "-d",
        db,
        "-f",
        str(sql_file),
    ]

    # nosec B603 - Explicit argument array with shell execution disabled prevents injection vulnerabilities
    subprocess.run(
        cmd,
        env=env,
        shell=False,
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantGrid Database Restore Utility")
    parser.add_argument("backup", help="Path to the backup file (.sql or .sql.gz)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
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
        confirm = input("\nThis will overwrite existing data.\nContinue? (yes/no): ")
        if confirm.strip().lower() != "yes":
            warn("Restore cancelled.")
            return

    sql = backup
    try:
        sql = extract_sql(backup)
        restore_database(sql)
        success("Database restored successfully.")

    except subprocess.CalledProcessError as e:
        error("Restore failed.")
        print(e)
    except Exception as e:
        error(f"An unexpected error occurred: {e}")
    finally:
        if sql != backup and sql.exists():
            sql.unlink()


if __name__ == "__main__":
    main()
