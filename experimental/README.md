# Experimental Services

This directory contains non-production experiments and placeholder services.

They are useful for learning, prototypes, or future service extraction, but they are not part of the supported production architecture.

Production architecture is:

`Nginx -> React frontend -> FastAPI trading-service -> Postgres/Redis`

Rules:

- Do not deploy anything in this directory to production.
- Do not route production traffic here.
- Do not treat demo auth or placeholder gateway behavior as security boundaries.
- Promote code out of `experimental/` only through an ADR, tests, CI, and owner review.
