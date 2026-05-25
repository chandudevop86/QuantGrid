# Testing Strategy

QuantGrid test categories:

- `tests/unit`: pure domain logic and small helpers.
- `tests/integration`: database, Redis, provider, and persistence checks.
- `tests/api`: FastAPI route behavior and auth.
- `tests/strategy`: strategy generation and scoring behavior.
- `tests/candle_validation`: market session and stale feed behavior.
- `tests/paper_execution`: paper order safety and rejection behavior.
- `tests/security`: auth, audit, secrets, roles, and config hardening.

Existing root-level tests remain supported during migration. New tests should be placed in the category directory that best matches their blast radius.
