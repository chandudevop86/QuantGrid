# Production release evidence

## Identity

- Release/tag and commit:
- Build/run ID:
- Approver:
- Deployment operator:
- Deployment time (IST):
- Previous commit and rollback command:

## Automated evidence

| Gate | Command | Result / artifact |
|---|---|---|
| Backend tests | `python -m pytest -q` | |
| Ruff | `python -m ruff check ...` | |
| Bandit | `python -m bandit -r ... -q` | |
| Dependency audit | `pip-audit` and `npm audit` | |
| Frontend checks | lint, type-check, unit, accessibility, E2E, build | |
| Compose | `bash deploy/scripts/validate-compose.sh` | |
| Terraform | fmt and validate | |
| Secret scan | repository security scanner | |

## Environment evidence

- HTTPS certificate and DNS checked:
- `/health` response checked without secrets:
- Database/Redis/worker healthy:
- Trading mode confirmed `paper`:
- Market data freshness checked:
- Monitoring test alert received:
- Backup file/checksum and off-host storage:
- Restore drill record:
- UAT record:

Do not paste tokens, passwords, database URLs, `.env` content, or rendered Compose configuration into this record. Secret rotation is recorded by vault item/version and timestamp only.
