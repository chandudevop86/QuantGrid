# Developer Guide

Rules for QuantGrid development:

- Keep QuantGrid focused on NIFTY options.
- Backend is the source of truth.
- Frontend must not calculate trading logic.
- Use deterministic, explainable rules.
- Prefer `No Trade` when uncertainty is high.
- No real broker orders from decision tests.
- Every decision change needs mock-data tests and documentation.

