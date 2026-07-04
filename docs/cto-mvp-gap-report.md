# QuantGrid CTO MVP Gap Report

Date: 2026-07-04

## Product Focus

QuantGrid is scoped as a NIFTY options decision assistant. The primary user promise is a decision in under 30 seconds: Buy CE, Buy PE, or No Trade, with confidence, risk, entry, stop loss, target, explanation, and invalidation level. Live trading remains disabled by default.

## Gaps Fixed In This Pass

| Area | Severity | Affected files | Current issue | Business risk | Fix |
| --- | --- | --- | --- | --- | --- |
| Risk management | High | `Backend/application/risk_engine.py`, `Backend/application/risk_gate.py` | Low liquidity was penalized in the decision engine but not centrally blocked by the risk engine. | Thin option books can create bad fills, slippage, and exits that invalidate the decision assistant promise. | Added `LOW_LIQUIDITY` blocker, warning text, and a rollout switch via `RiskLimits.block_low_liquidity`. |
| Paper/order lifecycle | Medium | `Backend/application/risk_gate.py` | Signal metadata for liquidity and expiry risk was not passed into the central order risk validation. | A valid dashboard warning could be lost before paper/live order validation. | Passed `liquidity`, `liquidity_status`, and `expiry_day` metadata into `RiskEngine.validate`. |
| Testing | Medium | `tests/test_risk_engine_contract.py` | Risk contract tests did not prove low-liquidity behavior. | Future changes could accidentally allow low-quality option entries. | Added blocking and warning-only regression tests. |

## Remaining CTO Gaps

| Area | Severity | Affected files/modules | Current issue | Business risk | Recommended fix |
| --- | --- | --- | --- | --- | --- |
| Decision pipeline wiring | High | `presentation/api/dashboard_api.py`, `application/decision_engine`, `application/risk_engine` | Dashboard decision uses environment-provided market factors instead of a typed market-data-to-decision adapter. | Decisions can be operator-dependent and hard to reproduce. | Add a `DecisionPipelineService` that maps candles, OI, PCR, VIX, FII/DII, GIFT NIFTY, and freshness into `DecisionInputs`. |
| Signal quality measurement | High | `application/signal_quality.py`, `application/analytics_service.py` | Metrics exist but are not fully tied to every Buy CE/Buy PE/No Trade recommendation. | Confidence can drift without precision/recall and false-positive tracking. | Persist decision outcomes and calculate precision, recall, false positives, false negatives, expectancy, profit factor, max drawdown, and regime-wise performance. |
| Explainability | Medium | `application/decision_engine/engine.py`, frontend dashboard | Explanation exists, but UI does not expose full supporting/opposing factor ledger and invalidation detail. | Traders may overtrust the headline recommendation. | Surface supporting factors, opposing factors, warnings, score reason, and invalidation level in the dashboard. |
| Market data quality | High | `application/data_quality_service.py`, `application/candle_validation.py`, providers | Freshness checks exist, but fallback/reconnect state is not a first-class status in the decision payload. | Stale or degraded feeds may be hard to diagnose during market hours. | Normalize feed health as LIVE, DEGRADED, STALE, CLOSED with provider, fallback, reconnect, and latest timestamp details. |
| Strategy governance | Medium | `domain/engine/strategy_engine.py`, strategy modules | Interfaces exist, but strategy versioning, rollout state, and audit trail are incomplete. | New strategy behavior can enter the system without traceability. | Add strategy registry metadata: version, enabled flag, rollout percent, validation result, and audit log. |
| Backtesting realism | Medium | backtesting modules/tests | Brokerage, slippage, spread, gap, expiry, and liquidity assumptions are not centrally documented in outputs. | Backtests may overstate trade quality. | Attach assumptions and cost model to every backtest summary. |
| Observability | Medium | `application/monitoring.py`, API logs | Decision logs exist, but dashboard API latency is static and decision/risk metrics are not complete. | Production diagnosis remains slower than required. | Record structured decision, risk-block, stale-data, and API latency metrics. |
| Security/config | Medium | `core/config.py`, `.env.example` | Live trading is guarded, but feature flags and profiles should be documented in one place. | Misconfiguration risk before beta. | Add central config docs and validate startup for required secrets in non-dev environments. |
| Documentation | Medium | `docs/`, `README.md` | Architecture and readiness docs exist, but decision/risk docs are fragmented. | New operators cannot understand why a recommendation was produced. | Add dedicated decision-engine and risk-engine docs with examples. |

## Current Decision Pipeline

Market Data -> Candle Validation -> Decision Engine -> Risk Engine/Risk Gate -> Recommendation -> Paper/Order Services -> Analytics.

The UI is mostly display-only for the decision assistant. Trading logic currently lives in backend services, not React components.

## How To Test

Run the focused decision and risk contract checks:

```bash
python -m pytest D:\QuantGrid\tests\test_risk_engine_contract.py D:\QuantGrid\tests\test_decision_engine.py
```

Expected result: all tests pass. A pytest cache permission warning may appear if `.pytest_cache` is not writable.

## Readiness Scores

| Dimension | Score | Reason |
| --- | ---: | --- |
| Product readiness | 72/100 | The core Buy CE/Buy PE/No Trade assistant exists, but factor ingestion and UI explainability need tightening. |
| Production readiness | 58/100 | Safety guards and tests are strong, but observability, configuration profiles, and deterministic data pipeline wiring need work. |
| Live trading readiness | 35/100 | Live trading should remain disabled. Broker safety exists, but signal provenance, replayability, and operational controls need a full hardening cycle. |

## 30-Day Roadmap

1. Build `DecisionPipelineService` with typed market data inputs and deterministic factor mapping.
2. Persist every recommendation and outcome for precision, recall, false positives, false negatives, expectancy, profit factor, and drawdown.
3. Surface supporting factors, opposing factors, warnings, score reason, and invalidation level in the dashboard.
4. Add strategy versioning, enable/disable state, rollout controls, and audit trail.
5. Add cost model assumptions to every backtest result: brokerage, slippage, spread, entry delay, gap, expiry, and liquidity filter.
6. Replace static dashboard API latency with measured latency and emit decision/risk/feed metrics.
7. Publish dedicated decision-engine and risk-engine operator docs.
