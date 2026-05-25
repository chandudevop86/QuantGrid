# Contributing

QuantGrid uses a small-company workflow: short-lived branches, pull requests, required CI, and explicit release gates.

## Branching

- `main` is always releasable.
- Use `feature/<short-name>` for product work.
- Use `bugfix/<short-name>` for defects.
- Use `hotfix/<short-name>` only for production incidents.

## Pull Requests

- Keep PRs focused and reviewable.
- Include tests or explain why tests are not appropriate.
- Update docs when behavior, deployment, configuration, or operations change.
- Do not commit secrets, local databases, generated build output, or pytest caches.

## Review Rules

- At least one reviewer is required for application changes.
- Security, execution, auth, broker, and deployment changes require an owner review.
- Reviewers should prioritize correctness, safety, observability, rollback, and testability.
- Do not merge with failing CI.
