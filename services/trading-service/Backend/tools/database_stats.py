from __future__ import annotations

import sys

from sqlalchemy import text
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


def success(msg):
    print(f"{Color.GREEN}{msg}{Color.END}")


def info(msg):
    print(f"{Color.CYAN}{msg}{Color.END}")


def error(msg):
    print(f"{Color.RED}{msg}{Color.END}")


def section(title):
    print()
    print(Color.BOLD + "=" * 80)
    print(title)
    print("=" * 80 + Color.END)


def fetch_value(db, sql):
    return db.execute(text(sql)).scalar()


def fetch_rows(db, sql):
    return db.execute(text(sql)).fetchall()


def main():

    validate_security_config()

    try:

        with SessionLocal() as db:

            section("QuantGrid Database Statistics")

            info("Database Information")

            print("Database :", fetch_value(db, "SELECT current_database();"))
            print("User     :", fetch_value(db, "SELECT current_user;"))
            print("Version  :", fetch_value(db, "SELECT version();"))

            section("Database Size")

            print(
                fetch_value(
                    db,
                    """
                    SELECT pg_size_pretty(pg_database_size(current_database()));
                    """,
                )
            )

            section("Connections")

            print(
                "Active Connections :",
                fetch_value(
                    db,
                    """
                    SELECT COUNT(*)
                    FROM pg_stat_activity;
                    """,
                ),
            )

            section("Table Sizes")

            rows = fetch_rows(
                db,
                """
                SELECT
                    relname,
                    pg_size_pretty(pg_total_relation_size(relid))
                FROM pg_catalog.pg_statio_user_tables
                ORDER BY pg_total_relation_size(relid) DESC;
                """,
            )

            for name, size in rows:
                print(f"{name:<35}{size}")

            section("Row Counts")

            tables = fetch_rows(
                db,
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname='public'
                ORDER BY tablename;
                """,
            )

            for (table,) in tables:

                try:
                    count = fetch_value(
                        db,
                        f'SELECT COUNT(*) FROM "{table}"'
                    )
                except Exception:
                    count = "?"

                print(f"{table:<35}{count}")

            section("Cache Hit Ratio")

            ratio = fetch_value(
                db,
                """
                SELECT ROUND(
                    SUM(blks_hit) * 100.0 /
                    NULLIF(SUM(blks_hit + blks_read),0),
                    2
                )
                FROM pg_stat_database;
                """,
            )

            print(f"Buffer Cache Hit : {ratio}%")

            section("Longest Running Queries")

            queries = fetch_rows(
                db,
                """
                SELECT
                    pid,
                    now()-query_start,
                    state,
                    LEFT(query,80)
                FROM pg_stat_activity
                WHERE state<>'idle'
                ORDER BY query_start;
                """,
            )

            if not queries:
                print("No active long-running queries.")
            else:
                for pid, runtime, state, query in queries:
                    print(f"{pid} | {runtime} | {state}")
                    print(query)
                    print()

            section("Index Usage")

            rows = fetch_rows(
                db,
                """
                SELECT
                    relname,
                    idx_scan
                FROM pg_stat_user_tables
                ORDER BY idx_scan DESC;
                """,
            )

            for table, scans in rows:
                print(f"{table:<35}{scans}")

            success("\nDatabase statistics collected successfully.")

    except SQLAlchemyError as e:

        error(str(e))
        sys.exit(1)

    except Exception as e:

        error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()