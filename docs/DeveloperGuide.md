# Developer Guide

Rules for QuantGrid development:

- Keep QuantGrid focused on NIFTY options.
- Backend is the source of truth.
- Frontend must not calculate trading logic.
- Use deterministic, explainable rules.
- Prefer `No Trade` when uncertainty is high.
- No real broker orders from decision tests.
- Every decision change needs mock-data tests and documentation.
- Trader-facing navigation stays limited to Dashboard, Market, Signals, Paper Trading, History, and Settings.
- Advanced pages remain available through Developer Mode route permissions for admin/developer users.
- Strategy selection must read plugin metadata from `StrategyEngine.registry()` instead of maintaining duplicate version maps.
