# QuantGrid retail-algo architecture and release policy

**Status: architecture proposal, not regulatory approval. No live execution authorization.**

## Regulatory constraints to verify with broker, exchange and Indian securities counsel

- SEBI retail algo circular February 4, 2025 and extension effective April 1, 2026: https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1759232056254.pdf
- NSE retail algo provider empanelment: https://www.nseindia.com/static/trade/empanelled-algo-providers-exchange
- NSE retail algo FAQ (broker-side strategy hosting, order origination, black-box RA obligations): https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQ_Retail%20Algo_03112025_NSE.pdf
- NSE trading member retail algo process: https://betanseapi.nseindia.com/static/trade/platform-services-non-neat-decision-support-tools-algorithm-trading

## Intended multi-client architecture

Client UI -> authenticated tenant gateway -> read-only market research -> strategy registry/version approval -> independent risk and compliance policy -> broker-hosted execution integration (subject to broker/exchange confirmation) -> broker RMS/exchange -> reconciliation -> immutable audit and customer reporting.

**Never treat research scores, LLM output, UI toggles or caller-provided booleans as order permission.**

## Models and methods

- Deterministic controls: exposure, lots, margin, market hours, contract master, idempotency, broker account binding, strategy version approval, kill switch.
- Market research: market regime and volatility classification, explainable technical features, calibrated probabilistic forecasts; compare against no-trade baselines.
- Options/futures: Greeks and IV surface, expiry-aware liquidity/slippage, OI changes, basis, margin and stress tests. Never assume PCR alone predicts direction.
- ML governance: point-in-time datasets, walk-forward splits, no lookahead or survivorship bias, out-of-sample validation, drift monitoring, reproducible versions and rollback.
- Execution: event-driven state machine, order-to-reservation binding, broker truth reconciliation, timeout/duplicate/fill race tests, per-tenant circuit breakers.
- Security: least-privilege broker tokens, per-tenant database row scoping, encryption, security scanning, pen testing, audit retention, incident and grievance processes.

## Release stages

1. Paper research: reproducible simulations and live-feed observation without orders.
2. Broker/exchange compliance review: legal classification, hosting and registration determination, written approvals, client disclosure and consent.
3. Broker sandbox/mock: approved algo identifiers, tags, risk control integration, failover and reconciliation tests.
4. Limited single-account pilot: only after independent authorized release, capital cap and kill switch; never enabled by this PR.
5. Multi-client pilot: tenant-isolation adversarial tests, separate broker identity and limits, approved infrastructure and documented incident procedures.

## Non-negotiable checks

CI, Security and CodeQL green; branch reviewed; approval evidence independently authenticated; regulatory and broker requirements met; zero unresolved critical vulnerabilities; independent risk approval; monitored rollback plan. Passing unit tests alone is insufficient.
