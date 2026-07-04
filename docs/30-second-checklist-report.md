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
- Discipline Engine blockers for sideways trading, late/chasing entries, big gaps, over-trading, consecutive-loss/revenge risk, duplicate signal, and missing price action confirmation.
- Paper-trade gate: paper trade is allowed only when checklist is at least 80, confidence is at least 75, risk passes, and discipline passes.
- Dashboard section for Trend, EMA, Volume, Support/Resistance, Risk-Reward, Confidence, Entry, SL, Target, Reason, Invalidation, System Status.

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
