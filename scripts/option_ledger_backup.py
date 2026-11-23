"""Consistent SQLite option-ledger snapshots alongside PostgreSQL archives."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity(path: Path) -> None:
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as database:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Option ledger integrity check failed")


def snapshot(archive: Path, source: Path) -> None:
    manifest = {"version": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
                "present": source.is_file()}
    target = Path(str(archive) + ".options.sqlite3")
    if source.is_file():
        descriptor, temporary = tempfile.mkstemp(prefix="option-backup-", dir=archive.parent)
        os.close(descriptor)
        try:
            with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as origin:
                with sqlite3.connect(temporary) as destination:
                    origin.backup(destination)
            _integrity(Path(temporary))
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        manifest.update(file=target.name, sha256=_checksum(target))
    manifest_path = Path(str(archive) + ".options.json")
    descriptor, temporary = tempfile.mkstemp(prefix="option-manifest-", dir=archive.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(manifest, stream, sort_keys=True)
        os.replace(temporary, manifest_path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def verify(archive: Path) -> Path | None:
    manifest_path = Path(str(archive) + ".options.json")
    if not manifest_path.is_file():
        return None  # PostgreSQL-only archives created before option support.
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("version") != 1 or type(manifest.get("present")) is not bool:
        raise ValueError("Invalid option backup manifest")
    if not manifest["present"]:
        return None
    expected = Path(str(archive) + ".options.sqlite3")
    if manifest.get("file") != expected.name or _checksum(expected) != manifest.get("sha256"):
        raise ValueError("Option backup checksum mismatch")
    _integrity(expected)
    return expected


def restore(archive: Path, target: Path) -> None:
    source = verify(archive)
    if source is None:
        return
    if target.exists() or not target.parent.is_dir():
        raise ValueError("Restore option ledger into a new file in an existing directory")
    descriptor, temporary = tempfile.mkstemp(prefix="option-restore-", dir=target.parent)
    os.close(descriptor)
    try:
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as origin:
            with sqlite3.connect(temporary) as destination:
                origin.backup(destination)
        _integrity(Path(temporary))
        # Hard-link publication fails if another process creates the target.
        os.link(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "verify", "restore", "restore-check"))
    parser.add_argument("archive", type=Path)
    parser.add_argument("ledger", nargs="?", type=Path)
    args = parser.parse_args()
    if args.action == "backup":
        if args.ledger is None:
            parser.error("backup requires the configured option ledger path")
        snapshot(args.archive, args.ledger)
    elif args.action == "restore":
        if verify(args.archive) is not None:
            if args.ledger is None:
                parser.error("RESTORE_OPTION_PAPER_LEDGER is required for this archive")
            restore(args.archive, args.ledger)
    elif args.action == "restore-check":
        if verify(args.archive) is not None:
            if args.ledger is None or args.ledger.exists() or not args.ledger.parent.is_dir():
                parser.error("RESTORE_OPTION_PAPER_LEDGER must name a new file in an existing directory")
    else:
        verify(args.archive)


if __name__ == "__main__":
    main()
