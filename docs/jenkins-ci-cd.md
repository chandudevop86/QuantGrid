# Jenkins CI/CD

Jenkins is supported alongside GitHub Actions for teams that deploy from an internal controller.

## Required Credentials

Configure these Jenkins credentials:

- `quantgrid-database-url`: secret text for `DATABASE_URL`.
- `quantgrid-auth-secret`: secret text for `QUANTGRID_AUTH_SECRET`.
- `quantgrid-ssh-deploy-key`: SSH private key for deployment hosts.
- `quantgrid-docker-registry`: username/password for the Docker registry.

## Pipeline Stages

1. Checkout
2. Backend setup
3. Backend lint with ruff
4. Backend tests with pytest
5. Security scan with bandit
6. Frontend install
7. Frontend build
8. Docker build validation
9. Smoke tests
10. Deploy to staging
11. Manual approval before production
12. Deploy production
13. Post-deploy smoke test
14. Rollback on failure

## Deployment Variables

Set these as Jenkins environment variables or folder-level configuration:

- `STAGING_HOST`
- `PRODUCTION_HOST`
- `DEPLOY_USER`
- `APP_DIR`
- `STAGING_URL`
- `PRODUCTION_URL`

Production deployment requires a manual `input` approval in the pipeline.
