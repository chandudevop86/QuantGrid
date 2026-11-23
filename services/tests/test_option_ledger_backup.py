import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


def _load():
    path = Path(__file__).resolve().parents[2] / "scripts/option_ledger_backup.py"
    spec = importlib.util.spec_from_file_location("option_ledger_backup", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wal_snapshot_preserves_committed_data_and_restores_new_target(tmp_path):
    backup = _load()
    source, archive = tmp_path / "source.sqlite3", tmp_path / "postgres.dump"
    with sqlite3.connect(source) as live:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("CREATE TABLE orders(id INTEGER PRIMARY KEY, premium REAL)")
        live.execute("INSERT INTO orders VALUES(1, 50)")
        live.commit()
        backup.snapshot(archive, source)
        live.execute("INSERT INTO orders VALUES(2, 60)")
        live.commit()
    saved = backup.verify(archive)
    with sqlite3.connect(saved) as snapshot:
        assert snapshot.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
    target = tmp_path / "restored.sqlite3"
    backup.restore(archive, target)
    with sqlite3.connect(target) as restored:
        assert restored.execute("SELECT premium FROM orders").fetchall() == [(50,)]
    with pytest.raises(ValueError, match="new file"):
        backup.restore(archive, target)


def test_missing_option_ledger_and_legacy_archive_are_supported(tmp_path):
    backup = _load()
    archive = tmp_path / "postgres.dump"
    assert backup.verify(archive) is None
    backup.snapshot(archive, tmp_path / "missing.sqlite3")
    assert backup.verify(archive) is None
    assert json.loads(Path(str(archive) + ".options.json").read_text())["present"] is False


def test_option_backup_tampering_is_rejected(tmp_path):
    backup = _load()
    source, archive = tmp_path / "source.sqlite3", tmp_path / "postgres.dump"
    with sqlite3.connect(source) as database:
        database.execute("CREATE TABLE orders(id INTEGER)")
    backup.snapshot(archive, source)
    saved = backup.verify(archive)
    saved.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        backup.verify(archive)
    manifest_path = Path(str(archive) + ".options.json")
    manifest = json.loads(manifest_path.read_text())
    manifest["file"] = "../other.sqlite3"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="checksum"):
        backup.verify(archive)
