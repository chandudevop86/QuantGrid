"""
QuantGrid :: Portfolio Management Module

Clean Architecture layout:
    domain/          -> Entities, value objects, enums, pure business/calculation logic (no I/O)
    infrastructure/   -> SQLAlchemy ORM models + Repository implementations (I/O)
    application/      -> Pydantic schemas (DTOs) + Services (use-case orchestration)
    api/              -> FastAPI routers (transport layer)

Nothing in `domain` imports from `infrastructure`, `application`, or `api`.
`application` depends only on `domain` (+ repository interfaces).
`infrastructure` implements the repository interfaces declared in `domain`.
`api` depends only on `application` (services/schemas) via Dependency Injection.
"""
