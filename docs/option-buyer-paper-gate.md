# NIFTY Option Buyer paper validation

The Option Buyer currently has no order submission action. The backend
`validate_option_paper_order` helper is deliberately pure and does not call
brokers, paper trade stores, or the existing basket execution service.

It rejects non-paper modes, missing contract identity, invalid expiry, stale
quotes, bad spreads, low OI, unsuitable delta/moneyness, invalid lot counts,
and premium exposures above a configurable threshold.

**Not yet approved for execution:** a real server endpoint must independently
fetch and verify security ID, expiry, exchange lot size, and live quote rather
than trust browser-supplied values. It must enforce authentication, authorization,
kill switch, capital limits, idempotency, and atomic persistence. The existing
generic basket endpoint must not be used as a shortcut for option orders.
Only after those controls and integration tests pass should a paper-only
submission button be enabled. Live broker routing is out of scope.
