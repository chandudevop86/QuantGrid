from __future__ import annotations

import sys

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from Backend.core.database import SessionLocal
from Backend.core.config import validate_security_config


class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


class Doctor:

    def __init__(self):
        self.score = 100
        self.warnings = []

    def ok(self, msg):
        print(f"{Color.GREEN}✔ {msg}{Color.END}")

    def warn(self, msg, penalty=5):
        self.score -= penalty
        self.warnings.append(msg)
        print(f"{Color.YELLOW}⚠ {msg}{Color.END}")

    def fail(self, msg, penalty=20):
        self.score -= penalty
        self.warnings.append(msg)
        print(f"{Color.RED}✖ {msg}{Color.END}")

    def info(self, msg):
        print(f"{Color.CYAN}➜ {msg}{Color.END}")


doctor = Doctor()


def check_connection(db):
    db.execute(text("SELECT 1"))
    doctor.ok("Database connection")


def check_tables(db):

    inspector = inspect(db.bind)
    tables = inspector.get_table_names()

    if not tables:
        doctor.fail("No tables found")
        return

    doctor.ok(f"{len(tables)} tables detected")


def check_extensions(db):

    extensions = db.execute(text("""
        SELECT extname
        FROM pg_extension
    """)).scalars().all()

    required = {
        "pgcrypto",
    }

    for ext in required:

        if ext in extensions:
            doctor.ok(f"Extension installed : {ext}")
        else:
            doctor.warn(f"Missing extension : {ext}")


def check_connections(db):

    active = db.execute(text("""
        SELECT COUNT(*)
        FROM pg_stat_activity
    """)).scalar()

    if active > 100:
        doctor.warn(f"High connection count ({active})")
    else:
        doctor.ok(f"Connections : {active}")


def check_cache(db):

    ratio = db.execute(text("""
    SELECT ROUND(
      SUM(blks_hit)*100/
      NULLIF(SUM(blks_hit+blks_read),0),2)
    FROM pg_stat_database;
    """)).scalar()

    if ratio is None:
        return

    if ratio < 95:
        doctor.warn(f"Cache hit ratio only {ratio}%")
    else:
        doctor.ok(f"Cache hit ratio {ratio}%")


def check_dead_tuples(db):

    rows = db.execute(text("""
    SELECT relname,n_dead_tup
    FROM pg_stat_user_tables;
    """)).fetchall()

    bad = False

    for table, dead in rows:

        if dead > 10000:
            doctor.warn(
                f"{table} has {dead} dead tuples",
                3,
            )
            bad = True

    if not bad:
        doctor.ok("No excessive dead tuples")


def check_index_usage(db):

    rows = db.execute(text("""
    SELECT
    relname,
    seq_scan,
    idx_scan
    FROM pg_stat_user_tables
    """)).fetchall()

    for table, seq, idx in rows:

        if seq > idx * 10:
            doctor.warn(
                f"{table} performing mostly sequential scans",
                2,
            )


def check_long_queries(db):

    rows = db.execute(text("""
    SELECT now()-query_start
    FROM pg_stat_activity
    WHERE state<>'idle'
    """)).fetchall()

    if len(rows):
        doctor.warn(
            f"{len(rows)} active queries running"
        )
    else:
        doctor.ok("No long running queries")


def summary():

    print()
    print("=" * 70)

    if doctor.score >= 95:
        color = Color.GREEN
        grade = "A+"

    elif doctor.score >= 90:
        color = Color.GREEN
        grade = "A"

    elif doctor.score >= 80:
        color = Color.YELLOW
        grade = "B"

    elif doctor.score >= 70:
        color = Color.YELLOW
        grade = "C"

    else:
        color = Color.RED
        grade = "FAIL"

    print(color + f"Database Health Score : {doctor.score}/100")
    print(f"Grade : {grade}" + Color.END)

    if doctor.warnings:

        print("\nRecommendations")

        for item in doctor.warnings:
            print(f" • {item}")

    else:

        print(Color.GREEN)
        print("No problems detected.")
        print(Color.END)


def main():

    print()
    print(Color.BOLD + "=" * 70)
    print("QuantGrid Database Doctor")
    print("=" * 70 + Color.END)

    validate_security_config()

    try:

        with SessionLocal() as db:

            check_connection(db)
            check_tables(db)
            check_extensions(db)
            check_connections(db)
            check_cache(db)
            check_dead_tuples(db)
            check_index_usage(db)
            check_long_queries(db)

        summary()

    except SQLAlchemyError as e:

        doctor.fail(str(e))
        summary()
        sys.exit(1)

    except Exception as e:

        doctor.fail(str(e))
        summary()
        sys.exit(1)


if __name__ == "__main__":
    main()