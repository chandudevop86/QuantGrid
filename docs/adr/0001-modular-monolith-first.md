# ADR 0001: Modular Monolith First

## Status

Accepted

## Context

QuantGrid has service-shaped experiments, but the real production value is currently concentrated in the FastAPI trading service and React dashboard. Running immature microservices would increase operational risk without improving reliability.

## Decision

QuantGrid will operate as a modular monolith:

`Nginx -> React frontend -> FastAPI trading-service -> Postgres/Redis`

Experimental services remain in `experimental/` and are explicitly non-production.

## Consequences

- CI/CD, deployment, and observability focus on one production backend.
- Domain modules can remain cleanly separated inside the trading service.
- Future service extraction requires a new ADR, ownership, SLOs, tests, and deployment runbooks.
