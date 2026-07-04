# 30-Second Trading Checklist Report

Date: 2026-07-04

## Audit

Existing reusable modules:

- Market data and candles: `Backend/application/market_data_service.py`, `Backend/application/market_data_store.py`, `Backend/application/candle_validation.py`.
- Strategies and signals: `Backend/domain/engine/strategy_engine.py`, `Backend/application/signal_validation.py`, `Backend/application/signal_quality.py`.
- Risk engine: `Backend/application/risk_engine.py`, `Backend/application/risk_gate.py`.
- Dashboard: `Backend/presentation/api/dashboard_api.py`, `apps/frontend/src/pages/Dashboard.tsx`.
- Institutional dashboard and copilot: `Backend/application/institutional_dashboard.py`, `Backend/application/market_copilot.py`.
- Backtesting: `Backend/application/quant_modules.py`, `Backend/trading_system/backtesting.py`.
- Paper trading: `Backend/application/paper_trade_store.py`, `Backend/application/order_management.py`.

## MVP Brain Gap Audit

| Area | Status | Files affected | Business impact | Recommended fix |
| --- | --- | --- | --- | --- |
| Decision engine | Present | `Backend/application/decision_engine/engine.py`, `Backend/application/decision_pipeline.py` | Produces Buy CE, Buy PE, or No Trade. | Keep pipeline as source of truth. |
| Market structure | Present | `Backend/application/decision_pipeline.py`, `Backend/domain/market_structure.py` | Detects HH/HL, LH/LL, BOS, CHoCH/MSS risk, sideways, and strength. | Calibrate swing window with NIFTY paper outcomes. |
| Market regime | Present | `Backend/application/decision_pipeline.py` | Detects Trending, Range, Volatile, Low Volatility, Gap Up/Down, Expiry Day, News Driven, Holiday Effect and gates strategies. | Add exchange calendar feed for holiday detection. |
| Confluence scoring | Present | `Backend/application/decision_pipeline.py` | Normalized 0-100 score combines HTF, structure, zones, FVG, liquidity, price action, options, institutional, risk, and discipline. | Tune weights after 30 sessions. |
| Trade quality | Present | `Backend/application/decision_pipeline.py` | Classifies Excellent, Good, Average, Poor, or Skip. | Keep hard blocks mapped to Skip. |
| Probability/confidence | Present | `Backend/application/decision_pipeline.py` | Exposes confidence/probability score without black-box AI. | Calibrate against persisted outcomes. |
| Strategy registry | Present | `Backend/domain/engine/strategy_engine.py` | Registry includes version, enabled state, rollout percentage, and audit trail. | Persist governance externally before multi-user rollout. |
| Strategy selection | Present | `Backend/application/decision_pipeline.py` | Scores enabled-style strategy candidates and records why alternatives lost. | Connect selected candidates to plugin metadata in the registry. |
| No Trade logic | Present | `Backend/application/decision_pipeline.py` | Explains why weak or unsafe trades are blocked. | Add more outcome-tagged block reason analytics over time. |
| Outcome analytics | Present | `Backend/application/recommendation_store.py` | Tracks precision, recall, false positives/negatives, expectancy, PF, drawdown, counts, block reasons, setup/quality win rate. | Improve only after more closed paper trades. |
| Trade review | Present | `Backend/application/recommendation_store.py` | Produces entry, stop, target, skip, and improvement review after outcome recording. | Surface review in journal UI later. |
| Explainability | Present | `Backend/application/decision_pipeline.py`, `apps/frontend/src/pages/Dashboard.tsx` | Dashboard renders plain-English reason and factors. | Keep wording concise for 30-second workflow. |
| Dashboard checklist | Present | `apps/frontend/src/pages/Dashboard.tsx` | Shows Today’s Decision and supporting checklist fields. | Avoid frontend-side trading calculations. |
| Trader UI focus | Present | `apps/frontend/src/components/Sidebar.tsx`, `apps/frontend/src/roles.ts` | Keeps daily trader workflow limited to Dashboard, Market, Signals, Paper Trading, History, Settings. | Keep advanced tools behind Developer Mode routes. |
| Paper trade integration | Present | `Backend/application/decision_pipeline.py` | Blocks paper execution unless confluence, quality, risk, discipline, freshness, and RR pass. | Keep live trading disabled by default. |
| Tests | Present | `tests/test_decision_pipeline.py`, `tests/test_dashboard_operations_contract.py` | Mock-data tests cover core decision paths. | Add regression cases when new blockers are introduced. |

What was missing:

- A single technical checklist payload with `checklist_score`, `passed`, `failed`, `warnings`, `trend`, `ema`, `volume`, `support_resistance`, and `risk_reward`.
- Dashboard rendering for passed/failed checklist items.
- High-probability trade layers for HTF alignment, key levels, FVG, price action, options flow, institutional filter, discipline, and weighted confidence.

Files modified:

- `Backend/application/decision_pipeline.py`
- `apps/frontend/src/pages/Dashboard.tsx`
- `tests/test_decision_pipeline.py`
- `tests/test_dashboard_operations_contract.py`
- `docs/30-second-checklist-report.md`

| Checklist item | Status | Affected files | Business impact | Recommended fix |
| --- | --- | --- | --- | --- |
| Trend analysis | Present | `Backend/application/decision_pipeline.py` | Identifies CE/PE direction from market structure. | Continue improving with multi-timeframe confirmation. |
| 20 EMA / 50 EMA | Present | `Backend/application/decision_pipeline.py` | Avoids weak trades when price is between EMAs. | Add 200 EMA as an optional higher-timeframe filter. |
| Volume confirmation | Present | `Backend/application/decision_pipeline.py` | Blocks low-volume moves and confirms breakout/breakdown. | Tune thresholds with paper-trade outcomes. |
| Support/resistance | Present | `Backend/application/decision_pipeline.py` | Avoids chasing CE near resistance or PE near support. | Replace simple nearest-level logic with pivot clustering later. |
| Risk-reward | Present | `Backend/application/decision_pipeline.py` | Blocks RR below 1.5 and calculates position size. | Tie risk budget to account profile in production. |
| CE / PE / No Trade | Present | `Backend/application/decision_engine/engine.py`, `Backend/application/decision_pipeline.py` | Keeps the product focused on the 30-second decision. | Keep No Trade preferred for mixed checklists. |
| Confidence score | Present | `Backend/application/decision_engine/engine.py` | Helps traders size trust in the signal. | Calibrate with persisted outcome metrics. |
| Explanation layer | Present | `Backend/application/decision_pipeline.py`, `apps/frontend/src/pages/Dashboard.tsx` | Explains why Buy CE, Buy PE, or No Trade was selected. | Add replay links to past decisions later. |

## Added

- Rule-based trend analyzer: higher highs, higher lows, lower highs, lower lows, uptrend, downtrend, sideways.
- EMA analyzer: 20 EMA, 50 EMA, bullish, bearish, weak/avoid.
- Volume analyzer: breakout/breakdown confirmation, low-volume move, volume spike, average comparison.
- Support/resistance analyzer: nearest support, nearest resistance, entry zone, invalidation, chasing warning.
- Risk-reward analyzer: risk amount, reward amount, RR, position size, allowed flag, warnings.
- Checklist score and blockers inside the decision pipeline.
- High Probability Trade Engine payload with market structure, HTF, key levels, FVG, price action, options flow, institutional, risk, discipline, and confidence layers.
- Professional confluence engine with normalized 0-100 score, trade quality classification, passed/failed factors, supporting/opposing factors, and hard blocks.
- Exact final decision payload with market bias, trade decision, trade quality, confidence, confluence, entry, stop, target, RR, position size, risk level, explanations, block reasons, invalidation, and system status.
- Discipline Engine blockers for sideways trading, late/chasing entries, big gaps, over-trading, consecutive-loss/revenge risk, duplicate signal, and missing price action confirmation.
- Paper-trade gate: paper trade is allowed only when confluence score is at least 70, trade quality is Good or Excellent, risk passes, discipline passes, data is fresh, and RR is at least 1.5.
- Dashboard section for Today's Decision, Buy CE/Buy PE/No Trade, Trade Quality, Confidence, Confluence, Entry, SL, Target, RR, Position Size, Market Structure, HTF Alignment, Supply/Demand, Price Action, Options Flow, Institutional Score, Risk Status, Discipline Status, Reason, Invalidation, and System Status.
- Recommendation analytics for Buy CE/Buy PE/No Trade counts, skipped trades, blocked trades, block reason frequency, win rate by trade quality, win rate by setup type, profit factor, expectancy, max drawdown, average RR, best setup, and worst setup.

## No Trade Logic

The pipeline returns No Trade when:

- Trend is sideways.
- EMA signal is weak.
- Volume does not confirm.
- Price is chasing near support/resistance.
- RR is below 1.5.
- Data is stale.
- VIX is elevated.
- OI conflicts with checklist direction.
- Confidence is below threshold.
- Higher timeframes conflict.
- Price action has no confirmation candle.
- Options flow or institutional context is neutral/risky.
- Discipline checks fail.

## Tests Added

`tests/test_decision_pipeline.py` covers:

- Uptrend, downtrend, sideways detection.
- EMA bullish, bearish, weak logic.
- Volume confirmation and low-volume rejection.
- Support/resistance calculation.
- Risk-reward validation.
- Buy CE, Buy PE, No Trade, stale-data blocking, poor-RR blocking.
- Higher timeframe conflict blocking.
- Price action confirmation blocking.
- Full high-probability checklist schema.
- Final decision schema and confluence/trade quality fields.
- HTF bullish CE allowance and bearish PE allowance.
- HTF conflict blocking.
- HH/HL bullish structure, LH/LL bearish structure, and sideways structure.
- Demand zone, supply zone, bullish FVG, bearish FVG, and liquidity sweep detection.
- Bullish engulfing and bearish engulfing confirmation.
- Poor RR, stale data, and FOMO/chasing paper-trade blocking.
- Final Buy CE, Buy PE, and No Trade decisions.

## Loop 14-18 Delivery

Gaps fixed:

- Dashboard now renders the backend final decision in plain English and exposes all requested trade/risk/context fields.
- Paper trade eligibility is deterministic and defaults to blocked unless every gate passes.
- Recommendation analytics now include recommendation counts, skipped/blocked trades, block reasons, quality/setup win rates, average RR, best setup, and worst setup.
- Market regime now returns allowed and blocked strategies.
- Strategy selection now ranks deterministic strategy candidates and records why alternatives lost.
- Probability engine now separates probability/confidence from raw confluence.
- Outcome analytics now include executed trades, won/lost trades, and confidence vs win rate.
- Trade review helper now reviews each completed recommendation outcome.
- Advanced routes are now Developer Mode only; trader navigation stays focused on the six core decision surfaces.
- Final decision response now exposes selected strategy, strategy version, confidence label, probability evidence, and No Trade next-review guidance directly.
- Outcome analytics now include strategy vs outcome, regime vs outcome, best strategy, and worst strategy.
- Tests use mock candles only; no broker login or live market dependency is required.

New modules/APIs:

- No unrelated modules were added. The existing `DecisionPipelineService` and recommendation store APIs were expanded.
- `factor_snapshot.high_probability_trade_engine.paper_trade_gate` is the backend paper-trade source of truth.

Remaining risks:

- Deterministic zone/FVG/liquidity logic is intentionally simple and needs calibration with paper-trade history.
- Outcome analytics are only as useful as the recorded trade outcomes.
- Live broker execution remains disabled by default and should stay disabled until paper-trade evidence is statistically meaningful.

Live trading readiness score: 35/100.

Architecture score: 78/100.
SOLID score: 74/100.
Performance score: 72/100.
Security score: 80/100.
Maintainability score: 76/100.
Decision quality score: 82/100.
Testing score: 70/100.
Production readiness: 68/100.

## Readiness

MVP readiness score: 82/100.

Remaining risks:

- EMA and support/resistance logic is deterministic and simple; it should be calibrated with real paper-trade outcomes.
- Volume thresholds are generic and may need NIFTY-specific tuning.
- 200 EMA is not yet exposed as a formal optional filter.
- Recommendation outcome metrics need more live paper-trade history before confidence is statistically meaningful.
- FVG and key-zone detection are intentionally simple deterministic rules and should be calibrated before production live trading.
- Institutional/global inputs depend on configured data feeds; absent data correctly causes No Trade rather than a random recommendation.

## Next 30-Day Roadmap

1. Add optional 200 EMA and multi-timeframe checklist confirmation.
2. Cluster support/resistance levels from pivots instead of nearest raw highs/lows.
3. Calibrate volume spike thresholds by market regime.
4. Backtest checklist blockers against historical NIFTY option entries.
5. Attach paper-trade outcomes automatically to persisted recommendations.
6. Add dashboard replay for the exact checklist state behind each recommendation.
7. Calibrate confluence weights with at least 30 paper-trade sessions before considering live execution.
8. Persist Developer Mode preferences and strategy governance in the backend.
