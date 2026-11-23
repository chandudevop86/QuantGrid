# PostgreSQL and option-ledger backups

`deploy/scripts/database-backup.sh backup` now writes the PostgreSQL archive,
its checksum, an option-ledger snapshot and an option manifest together in the
backup directory. `QUANTGRID_OPTION_PAPER_LEDGER` selects the SQLite source,
defaulting to the worker/backend's `Backend/data/option_paper.sqlite3` path.

SQLite's backup API captures committed data consistently, including WAL-mode
databases. The snapshot is integrity-checked and its SHA-256 digest is recorded
in `<archive>.options.json`. `verify` checks both archives. Older PostgreSQL-only
archives remain readable. If no option ledger exists, the manifest records that
fact. The snapshots are consistent individually; pause new trading entries for a
coordinated application-wide recovery point across both stores.

Restore still requires `ALLOW_DATABASE_RESTORE=YES` and `RESTORE_DATABASE_URL`.
If the archive includes option data, also provide `RESTORE_OPTION_PAPER_LEDGER`
pointing to a **new file in an existing directory**. The script validates this
target and the SQLite archive before PostgreSQL restore starts. It never replaces
an existing option ledger or its live WAL files. Validate the restored pair on a
disposable target, then stop the production services before switching both
configured storage targets together.

Keep the PostgreSQL archive, `.sha256`, `.options.sqlite3` and `.options.json`
files together in durable backup storage. A successful local snapshot does not
establish that off-host replication or a restore drill has completed.
