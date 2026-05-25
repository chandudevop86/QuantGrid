# Release Process

## Flow

1. Create `feature/<name>` or `bugfix/<name>`.
2. Open a PR.
3. Pass CI: backend lint, tests, security checks, frontend build, Docker validation.
4. Merge to `main`.
5. Tag release: `git tag v$(cat VERSION) && git push origin v$(cat VERSION)`.
6. Deploy staging.
7. Run smoke tests.
8. Approve production deployment.
9. Deploy production.
10. Run post-deploy smoke tests.

## Rollback

1. Identify the last known good tag.
2. Re-deploy that tag to staging.
3. Smoke test staging.
4. Re-deploy that tag to production.
5. Verify `/health`, `/metrics`, login, market validation, and paper execution.

## Versioning

- Patch: fixes and docs.
- Minor: compatible product/platform additions.
- Major: breaking API, deployment, data, or trading workflow changes.
