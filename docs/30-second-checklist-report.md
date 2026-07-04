# 30-Second Trading Checklist Report

Date: 2026-07-04

## Audit

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

## Tests Added

`tests/test_decision_pipeline.py` covers:

- Uptrend, downtrend, sideways detection.
- EMA bullish, bearish, weak logic.
- Volume confirmation and low-volume rejection.
- Support/resistance calculation.
- Risk-reward validation.
- Buy CE, Buy PE, No Trade, stale-data blocking, poor-RR blocking.

## Readiness

MVP readiness score: 82/100.

Remaining risks:

- EMA and support/resistance logic is deterministic and simple; it should be calibrated with real paper-trade outcomes.
- Volume thresholds are generic and may need NIFTY-specific tuning.
- 200 EMA is not yet exposed as a formal optional filter.
- Recommendation outcome metrics need more live paper-trade history before confidence is statistically meaningful.

## Next 30-Day Roadmap

1. Add optional 200 EMA and multi-timeframe checklist confirmation.
2. Cluster support/resistance levels from pivots instead of nearest raw highs/lows.
3. Calibrate volume spike thresholds by market regime.
4. Backtest checklist blockers against historical NIFTY option entries.
5. Attach paper-trade outcomes automatically to persisted recommendations.
6. Add dashboard replay for the exact checklist state behind each recommendation.
