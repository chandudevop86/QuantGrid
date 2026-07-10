# QuantGrid Product and Marketing Audit

**Audit date:** 2026-07-10  
**Mode:** Phase 1 repository audit only; no production code changed  
**Repository reviewed:** React/Vite frontend, FastAPI trading service, domain/application layers, providers, persistence, tests, CI/CD, Docker, Nginx, Terraform, and operational documentation.

## 1. Executive summary

QuantGrid already has a serious risk-first foundation: deterministic decision logic, explicit No Trade behavior, candle-freshness validation, paper execution, kill switches, broker guardrails, audit logging, role checks, structured monitoring, CI security gates, and 393 collected backend tests. It is not starting from a prototype-only codebase.

The primary problem is integration and product coherence. The platform currently presents several overlapping identities—options decision assistant, strategy laboratory, investing research suite, institutional dashboard, security console, operations console, and trading engine. The main dashboard exposes more than five conceptual sections, contains unavailable markets as repeated “Waiting” tiles, and mixes decision evidence, performance metrics, regimes, checklists, infrastructure, and narrative at equal visual weight.

The central decision pipeline is capable but does not yet implement the requested auditable “Trade Confidence” contract. Confidence factors do not consistently carry source, timestamp, availability, weight, and contribution. Higher-timeframe analysis is not trustworthy in the dashboard path because the same one-minute candle array is assigned to 1m, 5m, 15m, and 1h inputs. Options, FII/DII, VIX, Gift Nifty, and other contextual inputs are frequently environment variables or absent rather than synchronized provider observations.

The most important near-term outcome is not a new parallel engine. It is to consolidate existing decision, risk, data-quality, and explainability capabilities behind one typed dashboard-summary contract; make unavailable data explicit; make No Trade reason codes first-class; and reduce the default experience to Market Decision, Why This Decision, Trade Plan, Key Levels, and System Trust.

**Overall assessment:** strong safety-oriented MVP, incomplete product consolidation, not yet production-ready for live trading. Paper-mode decision support is the correct current posture.

## 2. Current product identity

### Current identities observed

- “NIFTY Options Decision Assistant” and “Buy CE, Buy PE, or No Trade” in the frontend shell.
- Risk-first “Disciplined Decisions” positioning and an explainable public landing experience.
- Strategy discovery/backtesting across breakout, mean reversion, supply/demand, MTF, BTST, CBT, CRT/TBS, and MTFA.
- Investing and “multibagger” research flows based partly on sample universes.
- Institutional, security, operations, job, broker, and admin consoles.

### Recommended category

> An explainable trading decision intelligence platform that combines market structure, volume, options data, probability, and risk to classify every setup as Bullish, Bearish, or No Trade.

### Memorable purpose

> Know the setup. Understand the risk. Trade only when conditions align.

### Concept to own

**Trade Confidence**—a traceable decision-readiness measure, not an implied probability of profit.

### Positioning constraint

QuantGrid must remain decision support. It must not be described as a tip provider, guaranteed-profit system, broker replacement, or autonomous money-making bot.

## 3. Current user journey

### Anonymous user

1. Sees product promise, workflow, risk-first differentiators, and disclaimer.
2. Authenticates from the shared top bar.

### Trader/viewer journey

1. Dashboard decision overview.
2. Market option chain.
3. Signals.
4. Paper trades and positions.
5. Backtest history.
6. Portfolio risk/settings route.

### Advanced journey

Advanced mode exposes candles, market copilot, order ticket, execution, strategies, jobs, institutional research, investing, trading engine, operations, and security. Admin additionally receives broker login and user management.

### Journey problems

- The default dashboard asks users to interpret too many panels rather than answer one decision question.
- “History” maps to backtesting, while trade history also exists in Trade Journal.
- “Risk & Settings” maps to a risk dashboard rather than actual settings.
- “Market” maps to option chain, while candles, data quality, and provider health live elsewhere.
- Normal roles include `trader`, `analyst`, `viewer`, and `ops`, while the desired product hierarchy specifies User, Analyst, Admin, and Developer. Role migration requires backward-compatible mapping.
- Implemented advanced pages are discoverable, but their quantity reinforces a platform/toolbox identity instead of one decision-intelligence category.

## 4. Core strengths

- `DecisionPipelineService` centralizes trend, EMA, volume, support/resistance, market structure, liquidity, price action, regime, options, institutional, discipline, risk/reward, confluence, and paper-trade gating.
- `DecisionEngine` explicitly supports Buy CE, Buy PE, and No Trade with a configurable confidence threshold.
- No Trade is already triggered for stale data, conflicts, weak confluence, poor risk/reward, invalid execution state, and risk blocking.
- Candle validation distinguishes live execution from after-market analysis and handles stale/delayed/closed/holiday states.
- Risk controls cover daily loss, trade count, stale signals, score thresholds, position sizing, spreads, news, portfolio exposure, consecutive losses, kill switch, duplicate orders, and broker circuit state.
- Paper orders, positions, trade journal, reconciliation, exit monitoring, and audit trails are implemented.
- Authentication uses signed tokens, role checks, minimum secret length, login rate limiting, and no default production credentials.
- Production configuration rejects SQLite, missing auth secrets, unconfigured risk inputs for live mode, and non-trading-grade Yahoo data unless explicitly overridden.
- CI runs Ruff, compile checks, Bandit, dependency audit, secret scanning, config guards, tests with coverage, frontend build, Compose validation, and Terraform validation.
- Deployment assets include static frontend delivery, Nginx TLS, private backend/database/cache bindings, health checks, staging, manual production approval, smoke tests, and rollback.
- The backend suite collects 393 tests across safety, strategies, providers, risk, auth, orders, positions, data quality, deployment, and observability.

## 5. Product gaps

### High priority

1. **Trade Confidence is not a stable product contract.** Confluence, probability, checklist score, decision confidence, qualification score, and strategy confidence coexist with different formulas and thresholds.
2. **The product hierarchy is too broad.** Investing, multibagger prediction, institutional tools, security operations, infrastructure operations, and strategy development compete with the core NIFTY decision workflow.
3. **No canonical dashboard-summary API exists.** The frontend consumes a large `/dashboard/operations` payload with nested implementation details and fallback aliases.
4. **No dedicated typed no-trade response exists.** No-trade intelligence is embedded in the decision pipeline and lacks stable codes, severity, and remediation contracts.
5. **Trade plans are always structurally present in decision outputs.** The API does not expose one explicit eligibility object that guarantees plans are absent when conditions fail.

### Medium priority

- Product terminology varies: Buy CE/PE, CE/PE Watch, bullish/bearish, signal, recommendation, trade decision, market bias, and strategy selection.
- “Probability” can be read as probability of profit even though the calculation is a deterministic heuristic.
- No explicit product boundary separates educational/paper/backtested/simulated/live values across all pages.

## 6. Trust gaps

1. **Higher-timeframe evidence is not genuine in the dashboard path.** `from_environment()` assigns the same candle list to `candles_1m`, `candles_5m`, `candles_15m`, and `candles_1h`. HTF agreement derived from these aliases can overstate confluence.
2. **Environment variables stand in for synchronized market observations.** PCR, VIX, FII/DII, Gift Nifty, VWAP relation, OI bias, and liquidity can come from process configuration without per-observation source or timestamp.
3. **Synthetic option-chain fallback exists.** The fallback is labeled “display only,” which is positive, but it shares compatibility fields with live data and can still be rendered by ordinary UI flows. It must never contribute to eligibility or confidence.
4. **Sample market/backtest/investing datasets exist.** Sample fallback is guarded in some market endpoints, but sample universes remain default inputs for investing pages. Every sample-derived result needs an unavoidable simulated/sample label.
5. **Missing dashboard markets appear as “Waiting.”** BANK NIFTY, FIN NIFTY, USDINR, Crude, and US Futures are static placeholder tiles. This creates an impression of pending integration rather than explicit unavailability.
6. **Hardcoded observability and backtest context fields exist.** Dashboard operations returns zeros for signal metrics, rejected orders, historical win rate, and Sharpe ratio. Zero is a valid measurement and should not represent “not connected.”
7. **Broker health is configuration health.** Dashboard “connected” derives from `settings.broker_configured`, not a confirmed live session.
8. **Worker health is tautological.** `count_jobs("running") >= 0` is always true.

## 7. UX gaps

- The authenticated dashboard contains market snapshot, hero decision, 15-field decision grid, three factor panels, decision quality, narrative, three regime cards, ten-row checklist, market/signal/system panels, and system status—well above the requested five primary sections.
- Evidence is summarized in strings rather than a consistent factor model with value, direction, weight, contribution, source, timestamp, and availability.
- Data freshness is visible in several places but not one persistent, dominant trust state.
- Stale/provider-unavailable/missing-data states are implemented inconsistently across pages.
- Detailed metrics are not consistently moved into expandable advanced panels.
- The frontend relies heavily on color tones; some pills include text, but a formal color-independent accessibility audit is absent.
- Search navigates by route name but is not a search of instruments, decisions, or evidence.
- The default navigation has six concepts and advanced mode has many more, rather than the requested seven consolidated destinations.
- Several pages duplicate metric-card and status presentation patterns instead of using a small typed component system.

## 8. Technical gaps

### Architecture and contracts

- The repository has both `Backend/application` and `Backend/app` namespaces, increasing discovery cost and encouraging parallel implementations.
- Decision calculations are distributed across `decision_engine`, `decision_pipeline`, qualification, signal validation, risk engine, and strategy-specific confidence calculations.
- API paths use overlapping prefixed and compatibility aliases (`/api/...` and unprefixed routes), with no consistent response envelope.
- The dashboard response is a large untyped dictionary assembled directly in the route.
- Store initialization still uses runtime `Base.metadata.create_all()` in order, backtest-job, and kill-switch paths. Startup/migrations should own schema changes.
- `Base.metadata.create_all()` is not a production migration strategy; no Alembic-style versioned migration flow is evident.

### Frontend maintainability

- `apps/frontend/routes.tsx` is redundant with `src/App.tsx` and appears unused by `src/main.tsx`.
- `src/pages/job.tsx` appears unused alongside `Jobs.tsx`.
- `MetricCard.tsx` appears unused while pages define local metric-card structures.
- `AutoSignals.ts` is only a re-export alias; compatibility intent should be documented or it should be removed later.
- The frontend has no dedicated lint, unit-test, component-test, or end-to-end-test script; `npm run build` is the only package quality gate.

### Performance and resilience

- Topbar, MarketStatusBanner, Dashboard, and SystemHealthWidget independently request the expensive operations payload, while WebSocket also emits it. A shared query/status provider is needed.
- The dashboard endpoint performs decision computation, persistence, risk summary, DB checks, strategy checks, job counts, and observability assembly synchronously.
- Compatibility fallbacks in the API client can double-request during failures and obscure which contract is authoritative.

## 9. Data-quality gaps

Existing validators correctly check individual OHLC relationships, positive prices, nonnegative volume, basic option leg constraints, provider completeness, freshness/fallback penalties, and missing fundamentals.

Missing or incomplete centralized checks:

- Duplicate candle timestamps.
- Out-of-order records.
- Expected-interval gaps and insufficient history.
- Cross-row unexplained price gaps.
- Explicit timezone consistency across a series.
- Market-session membership in the general data-quality report.
- Zero-volume warnings during active sessions (zero is currently valid).
- Option expiry correctness and expiry freshness.
- Strike ordering and duplicate strikes.
- Bid/ask crossing, width, and liquidity validation in the general option-chain model.
- Open-interest consistency and completeness across strikes.
- A single usability result consumed by the decision eligibility gate.

The dashboard decision pipeline validates candle freshness but does not consume the aggregate data-quality dashboard score. Critical option/provider failures therefore are not represented through one centralized blocking contract.

## 10. Security gaps

### Strengths

- Production secret, database, broker, risk, CORS, and data-provider guards.
- Role-protected APIs and admin operations.
- Login throttling, audit logs, secret sanitization, secret scanning, Bandit, and dependency auditing.
- Nginx configuration includes TLS, HSTS, frame denial, MIME sniffing protection, referrer policy, and permissions policy.
- Redis, Postgres, backend, and frontend container ports bind to loopback interfaces.
- Live execution is server-authorized and cannot be enabled solely by frontend state.

### Gaps

- Browser tokens are stored in `localStorage`, increasing impact if an XSS defect is introduced. HttpOnly secure same-site cookies or a carefully documented threat model should be considered.
- Nginx does not define a Content Security Policy.
- The authenticated dashboard DB-health message can include raw exception text.
- Docker Compose provides a predictable local Postgres password fallback. It is acceptable only when the file is explicitly treated as local development and production validation rejects defaults.
- Broker credentials can be entered through the UI; storage, rotation, expiration, and operator visibility require a formal secrets-management design.
- Security UI reports configuration findings, but this is not equivalent to continuous infrastructure scanning.

## 11. Features to retain

- Deterministic Buy CE / Buy PE / No Trade decision engine.
- Candle/session/freshness validation.
- Market structure, EMA, volume, VWAP, support/resistance, liquidity, regime, and price-action analysis.
- Options positioning when sourced from a validated provider.
- Explainability, blockers, wait-for conditions, and invalidation levels.
- Central risk manager, risk/reward checks, lot rounding, duplicate prevention, cooldown, kill switch, broker circuit breaker, and live guardrails.
- Paper trading, positions, journal, exits, reconciliation, and backtesting.
- Role-based authentication, audit logging, observability, and operational health.
- Provider interfaces and strategy registry/governance.
- CI/CD safety, staging approval, smoke testing, and rollback.

## 12. Features to simplify

- Collapse checklist, narrative, supporting/opposing cards, and decision-quality metrics into one **Why This Decision** evidence panel.
- Merge market status, data freshness, provider state, infrastructure health, risk state, and execution mode into **System Trust**.
- Consolidate Trade, Execution, Trading Engine, and active positions under **Trade Plans** and **Paper Trading**, with live controls admin-gated.
- Consolidate Candles, Option Chain, Institutional, and data-quality details under **Live Analysis**.
- Consolidate Strategies, Jobs, and developer diagnostics under Advanced/Developer tools.
- Replace multiple confidence-like fields with one Trade Confidence result plus clearly named supporting sub-scores.
- Replace raw “Waiting” tiles with explicit `Unavailable`, `Not configured`, or `Delayed` states.

## 13. Features to remove or defer

Remove from the default product journey, not necessarily from code:

- Multibagger prediction and broad investing research until the core options decision product is trusted.
- Institutional and global-context tiles without synchronized providers.
- Synthetic option-chain display in normal trader mode.
- Placeholder BANK NIFTY, FIN NIFTY, USDINR, Crude, and US Futures tiles.
- Security and infrastructure consoles from non-admin navigation.
- Live trading promotion until TLS, broker connectivity, provider quality, reconciliation, monitoring, backups, and the production checklist are verified.

Defer physical deletion until route usage, customer need, and compatibility are measured.

## 14. Recommended product hierarchy

### Primary navigation

1. **Dashboard** — five-section decision summary.
2. **Live Analysis** — charts, option chain, volume, evidence, and data quality.
3. **Trade Plans** — eligible plans, invalidation, expiry, and required conditions.
4. **Paper Trading** — orders, positions, exits, journal, and review.
5. **Backtesting** — validated historical experiments with cost assumptions and simulated labels.
6. **System Health** — provider, data, risk, broker, job, DB, API, and kill-switch trust.
7. **Settings** — user preferences and admin-gated risk/provider configuration.

### Default dashboard

1. Market Decision.
2. Why This Decision.
3. Trade Plan (only when eligible).
4. Key Levels.
5. System Trust.

### Roles

- **User:** dashboard, live analysis, trade plans, paper trading, backtesting.
- **Analyst:** User plus deeper evidence and research tools.
- **Admin:** operational health, users, risk configuration, broker configuration, audit.
- **Developer:** raw payloads, strategies, jobs, diagnostics, feature development.

Map existing `trader` and `viewer` to User and `ops` to Admin/operations capabilities during migration; do not invalidate existing tokens without a transition plan.

## 15. Prioritized implementation plan

### P0 — Trust and truthfulness

1. Define canonical terms: Bullish/Bearish/Neutral/Uncertain; CE Watch/PE Watch/No Trade; Trade Confidence; Eligible/Blocked.
2. Remove placeholder markets and hardcoded zero metrics from trader-facing responses.
3. Prevent synthetic/sample/fallback data from contributing to any recommendation or trade plan.
4. Fetch and validate real timeframe-specific candle series; block HTF factors when unavailable.
5. Create one `DataQualityResult` with critical blockers and feed it into decision eligibility.
6. Make live broker status a real session check, not credential presence.

### P1 — Contract consolidation

1. Add typed models around existing logic: confidence factor/breakdown/result, data quality, eligibility, structured no-trade reason, key level, trade plan, and system trust.
2. Build `/product/dashboard-summary` as an adapter over current services; preserve existing routes during migration.
3. Add factor source, timestamp, availability, value, weight, contribution, and explanation.
4. Separate confidence from probability of profit; remove percentage language where validation is absent.
5. Emit a trade plan only when a single eligibility gate passes every critical rule.

### P1 — Dashboard simplification

1. Implement the five-section hierarchy.
2. Move raw diagnostics and secondary metrics into expandable Advanced content.
3. Consolidate navigation into seven destinations with role-aware subnavigation.
4. Add consistent stale, missing, provider-down, simulated, delayed, backtested, and empty states.
5. Add permanent risk disclosure and mode/source badges.

### P2 — Engineering hardening

1. Replace runtime schema creation with versioned migrations.
2. Introduce a shared frontend status/query provider to eliminate duplicate operations requests.
3. Establish one canonical API envelope and error model.
4. Add frontend ESLint, component tests, accessibility tests, and Playwright smoke tests.
5. Raise backend coverage based on risk-critical modules rather than a blanket percentage alone.
6. Add CSP and document token-storage threat decisions.

### P3 — Deferred expansion

Reassess investing, multibagger, institutional, and autonomous-engine surfaces only after the core decision workflow has measured paper-trading reliability and user comprehension.

## 16. Risks and assumptions

- This audit evaluates code and configuration, not the validity or profitability of trading strategies.
- No live-provider credentials or live market session were used; provider behavior must be verified in staging during market hours.
- Backtests may contain statistical and market-microstructure bias beyond code-level checks.
- A heuristic confidence score is not a calibrated probability of profit.
- Sample and synthetic modules may be intentional development tools; the risk is their proximity to normal product flows.
- The checked-in Nginx TLS configuration is stronger than the previously observed public HTTP deployment; production state may lag repository configuration.
- Production readiness remains incomplete because the repository checklist is entirely unchecked.
- The frontend build is validated by CI design, but behavioral/accessibility coverage is absent.

## Audit completion matrix

| Area | Status | Evidence | Remaining Gap |
| --- | --- | --- | --- |
| Product positioning | Partial | Public landing copy and decision-assistant shell | Multiple competing product identities |
| Dashboard simplification | Gap | `Dashboard.tsx` renders more than five primary concepts | Consolidate into five sections |
| Confidence engine | Partial | Decision engine, confluence, probability, checklist, qualification | One typed, source-aware Trade Confidence contract |
| No-trade engine | Partial | Embedded blockers and no-trade intelligence | Stable codes, severity, remediation, dedicated contract |
| Explainability | Partial | Supporting/opposing factors, narrative, wait-for conditions | Per-factor value/source/time/contribution |
| Data quality | Partial | Candle, option, provider, and fundamental validators | Cross-row checks and centralized eligibility consumption |
| Risk management | Strong | Central risk manager, execution guards, kill switch, tests | Consolidate configuration and prove staging behavior |
| Frontend UX | Partial | Responsive React UI and explicit state components | Five-section hierarchy and accessibility tests |
| API contracts | Gap | Many functional endpoints and compatibility aliases | Canonical typed envelope and dashboard adapter |
| Testing | Strong backend / Gap frontend | 393 backend tests collected; CI coverage gate 45% | Behavioral frontend, a11y, E2E, higher risk-based coverage |
| Security | Partial | Config guards, RBAC, audit, TLS config, scans | CSP, token-storage hardening, secrets lifecycle |
| Observability | Partial | Structured logs, Prometheus metrics, health, runbooks | Remove hardcoded dashboard metrics; decision/data-quality distributions |
| Documentation | Partial | Architecture, deployment, risk, decision, testing, runbooks | Requested product/confidence/no-trade/API design docs |
| Production readiness | Not complete | Checklist and deployment automation exist | Checklist unchecked; live provider/TLS/backups/restore evidence required |

## Evidence index

- Frontend composition and routes: `apps/frontend/src/App.tsx`, `apps/frontend/src/pages/Dashboard.tsx`, `apps/frontend/src/components/Sidebar.tsx`, `apps/frontend/src/roles.ts`.
- Decision and explainability: `services/trading-service/Backend/application/decision_engine/engine.py`, `services/trading-service/Backend/application/decision_pipeline.py`.
- Data quality and freshness: `services/trading-service/Backend/application/candle_validation.py`, `services/trading-service/app/validation/data_quality.py`, `services/trading-service/Backend/application/data_quality_service.py`.
- Providers and fallbacks: `services/trading-service/Backend/application/market_data_service.py`, `services/trading-service/Backend/application/quant_modules.py`, `services/trading-service/Backend/presentation/api/market_api.py`.
- Risk and execution: `services/trading-service/Backend/application/central_risk_manager.py`, `services/trading-service/Backend/presentation/api/execution.py`, `services/trading-service/Backend/application/kill_switch.py`.
- API assembly: `services/trading-service/Backend/presentation/api/dashboard_api.py`, `services/trading-service/Backend/presentation/api/main.py`.
- Security/configuration: `services/trading-service/Backend/core/config.py`, `services/trading-service/Backend/presentation/api/auth.py`, `deploy/nginx/quantgrid.conf`.
- Delivery: `.github/workflows/ci.yml`, `Jenkinsfile`, `docker-compose.app.yml`, `deploy/scripts/`, `docs/production-readiness-checklist.md`.
- Test inventory: 393 tests collected with `python -m pytest --collect-only -q` on 2026-07-10.
