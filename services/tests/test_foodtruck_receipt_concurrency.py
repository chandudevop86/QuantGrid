"""Food Truck receipt allocation regression and optional real PostgreSQL lock test."""
import ast
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "services/foodtruck-api/app/main.py"
LOCK_SQL = "SELECT pg_advisory_xact_lock(6211991)"


def test_both_receipt_allocation_paths_acquire_same_transaction_lock():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    paths = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = ast.get_source_segment(SOURCE.read_text(encoding="utf-8"), node) or ""
        if "INSERT INTO orders" not in body:
            continue
        assert LOCK_SQL in body, f"{node.name} allocates receipt without shared lock"
        assert body.index(LOCK_SQL) < body.index("SELECT 1 FROM orders"), node.name
        paths.append(node.name)
    assert len(paths) == 2, f"Expected two receipt paths, found {paths}"


def test_postgres_transaction_lock_blocks_concurrent_allocation():
    url = os.getenv("QUANTGRID_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set QUANTGRID_TEST_POSTGRES_URL to run real PostgreSQL concurrency test")
    engine = create_engine(url, pool_size=2, max_overflow=0, pool_timeout=5)
    try:
        if engine.dialect.name != "postgresql":
            pytest.fail("Concurrency test requires real PostgreSQL")
        with engine.begin() as first:
            first.execute(text(LOCK_SQL))
            with engine.connect() as second:
                # A second connection cannot acquire the receipt lock while
                # the first transaction holds it.
                assert second.execute(text("SELECT pg_try_advisory_xact_lock(6211991)")).scalar_one() is False
        with engine.begin() as after_commit:
            assert after_commit.execute(text("SELECT pg_try_advisory_xact_lock(6211991)")).scalar_one() is True
    finally:
        engine.dispose()
