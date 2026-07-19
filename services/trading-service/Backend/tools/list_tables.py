from __future__ import annotations

import re
import sys
from urllib.parse import urlsplit

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from Backend.core.database import SessionLocal
from Backend.core.config import validate_security_config


class Color:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def success(msg: str):
    print(f"{Color.GREEN}{msg}{Color.END}")


def info(msg: str):
    print(f"{Color.CYAN}{msg}{Color.END}")


def warn(msg: str):
    print(f"{Color.YELLOW}{msg}{Color.END}")


def error(msg: str):
    print(f"{Color.RED}{msg}{Color.END}")


def main():

    validate_security_config()

    print()
    print(Color.BOLD + "=" * 90)
    print("                    QuantGrid Database Tables")
    print("=" * 90 + Color.END)

    try:

        with SessionLocal() as db:

            inspector = inspect(db.bind)

            tables = sorted(inspector.get_table_names())

            if not tables:
                warn("No tables found.")
                return

            info(f"Total Tables : {len(tables)}")
            print()

            for table in tables:

                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
                    raise ValueError(table)

                try:
                    rows = db.execute(
                        text(f'SELECT COUNT(*) FROM "{table}"')  # nosec B608
                    ).scalar()

                except Exception:
                    rows = "N/A"

                print(Color.BOLD + "-" * 90 + Color.END)
                print(f"Table : {table}")
                print(f"Rows  : {rows}")

                columns = inspector.get_columns(table)

                print("\nColumns")

                for col in columns:

                    nullable = "YES" if col["nullable"] else "NO"

                    print(
                        f"  • {col['name']:<25}"
                        f"{str(col['type']):<20}"
                        f"NULL:{nullable}"
                    )

                pk = inspector.get_pk_constraint(table)

                if pk["constrained_columns"]:
                    print("\nPrimary Key")
                    print("  " + ", ".join(pk["constrained_columns"]))

                indexes = inspector.get_indexes(table)

                if indexes:

                    print("\nIndexes")

                    for idx in indexes:

                        print(
                            f"  • {idx['name']} "
                            f"({', '.join(idx['column_names'])})"
                        )

                print()

        success("Database schema inspection completed successfully.")

    except SQLAlchemyError as exc:

        error(str(exc))
        sys.exit(1)

    except Exception as exc:

        error(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
