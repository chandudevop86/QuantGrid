# Database backup and restore

QuantGrid backups are PostgreSQL custom-format archives with a SHA-256 checksum. Store them outside the application server in encrypted, access-controlled storage.

## Create and verify a backup

```bash
cd /root/QuantGrid
bash deploy/scripts/database-backup.sh backup
bash deploy/scripts/database-backup.sh verify backups/quantgrid-YYYYMMDDTHHMMSSZ.dump
```

The script reads `DATABASE_URL` from the environment or the protected trading-service `.env`, creates the archive with mode `0600`, validates its catalog, and writes a checksum.

## Restore drill

Always restore into a disposable or staging database first. The restore command deliberately ignores `DATABASE_URL`; it requires a separate target and an explicit authorization marker.

```bash
export RESTORE_DATABASE_URL='postgresql://user:password@staging-db/quantgrid_restore'
export ALLOW_DATABASE_RESTORE=YES
bash deploy/scripts/database-backup.sh restore backups/quantgrid-YYYYMMDDTHHMMSSZ.dump
QUANTGRID_ENV_FILE=/path/to/restore.env bash deploy/scripts/database.sh check
```

Record the archive checksum, start/end time, restored migration version, row-count spot checks, and operator approval in the release evidence. Never paste database URLs or command output containing credentials into tickets or CI logs.

## Retention and recovery target

- Daily encrypted backup, retained for 30 days.
- Weekly encrypted backup, retained for 12 weeks.
- Quarterly restore drill in a non-production account.
- Initial operating targets: RPO 24 hours and RTO 4 hours, tightened only after measured restore drills.

## Application rollback

Record the deployed and previous Git commits. Roll back application code with:

```bash
bash deploy/scripts/deploy-production.sh --rollback <previous-commit>
```

Schema changes must remain backward compatible across one application release. If a schema rollback is ever required, stop writers, take a fresh backup, obtain incident-commander approval, and restore into a new database rather than destructively improvising on production.
