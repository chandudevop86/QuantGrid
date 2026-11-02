# QuantGrid: Indian securities regulatory readiness (draft, November 2026)

This is a **regulatory engineering checklist**, not SEBI registration, approval, or legal advice. Obtain written advice from qualified Indian securities counsel and the sponsoring broker/exchange before offering client-facing automated trading or investment advice.

## Business model decision

1. Internal research/paper trading: document data licensing and privacy requirements.
2. Research sold to clients: assess Research Analyst registration, qualifications, disclosures, conflicts, records and advertising requirements.
3. Personalized recommendations: assess Investment Adviser registration, suitability, risk profiling, agreements, fees and grievance duties.
4. Broker-connected client algos: obtain broker/exchange determination of algo provider empanelment, strategy registration, API implementation standards and testing requirements.
5. Operating as a broker: separate stockbroker registration and exchange membership assessment.

## Official regulatory sources (verify current consolidated versions before launch)

- SEBI retail algo circular (2025-02-04): https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html
- SEBI implementation extension (2025-09-30): https://www.sebi.gov.in/legal/circulars/sep-2025/extension-of-timeline-for-implementation-of-sebi-circular-dated-february-04-2025-on-safer-participation-of-retail-investors-in-algorithmic-trading-_96979.html
- NSE algo provider rules: https://www.nseindia.com/static/trade/empanelled-algo-providers-exchange
- SEBI Investment Adviser regulations: https://www.sebi.gov.in/legal/regulations/aug-2025/securities-and-exchange-board-of-india-investment-advisers-regulations-2013-last-amended-on-august-7-2025-_96112.html
- SEBI Research Analyst regulations: https://www.sebi.gov.in/legal/regulations/aug-2025/securities-and-exchange-board-of-india-research-analysts-regulations-2014-last-amended-on-august-6-2025-_96110.html
- SEBI cyber resilience clarifications: https://www.sebi.gov.in/legal/circulars/apr-2025/clarifications-to-cybersecurity-and-cyber-resilience-framework-cscrf-for-sebi-regulated-entities-res-_93734.html
- SEBI technical glitches circular (2026-01-09): https://www.sebi.gov.in/legal/circulars/jan-2026/review-of-framework-to-address-the-technical-glitches-in-stock-brokers-electronic-trading-systems_99006.html

## Engineering controls and known unverified gaps

- Strong tenant ID scoping in every query, cache key, worker task, audit event and order lookup; add cross-tenant adversarial tests.
- Per-client broker credentials stored encrypted, rotated and never exposed to other clients or frontend logs.
- Server-authoritative broker identity, contract master, exchange approval, position reconciliation and idempotent order lifecycle.
- Per-client and global limits for exposure, drawdown, margin, orders/second, kill switch and risk profile.
- Immutable, time-synchronized records for client consent, algo versions, recommendations, order decisions, approvals and incidents.
- Incident handling, breach notification analysis, BCP/DR tests, grievance workflow and data retention/deletion policy.
- Licensed market data, entitlements, redistribution restrictions and clear distinction between research and personalized advice.
- Security scanning and external penetration test before multi-client launch.

The current gate only evaluates **self-reported checklist values** and never authorizes launch. Production requires cryptographically attributable evidence, an independently authorized approval register and legal/broker sign-off. A passing test is not proof of compliance.
