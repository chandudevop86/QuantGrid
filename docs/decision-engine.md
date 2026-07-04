# Decision Engine Operator Guide

QuantGrid's decision engine produces one of three NIFTY options actions:

- Buy CE
- Buy PE
- No Trade

No Trade is a valid and preferred output when signals conflict, confidence is weak, data is stale, or risk controls block the setup.

## Pipeline

Market Data -> Validation -> DecisionPipelineService -> DecisionEngine -> Risk Engine -> Recommendation -> Paper Trade -> Analytics.

`DecisionPipelineService` owns deterministic factor mapping. The dashboard only displays the resulting decision.

## Inputs

The pipeline maps these factors into `DecisionInputs`:

- Trend
- Momentum
- VWAP relation
- Price action
- Support and resistance
- OI bias
- PCR
- Max Pain
- India VIX
- FII/DII bias
- GIFT NIFTY bias
- Liquidity
- Expiry-day flag
- Data freshness and market session state

## Outputs

Every decision includes:

- Market bias
- Buy CE, Buy PE, or No Trade
- Confidence
- Entry zone
- Stop loss
- Target
- Risk level
- Explanation
- Invalidation level
- Supporting factors
- Opposing factors
- Warnings
- Data status: LIVE, DEGRADED, STALE, CLOSED
- Score reason
- Probability score
- Trade quality
- Strategy selection
- No Trade intelligence
- Explainability payload
- Confidence label
- Selected strategy version

## Operating Rules

- Block signals when data is stale.
- Prefer No Trade when directional factors conflict.
- Keep live trading disabled unless all live safety gates are explicitly configured.
- Treat elevated VIX, expiry risk, and low liquidity as quality reducers or blockers.
- Use the backend `explainability.plain_english` text as the dashboard reason.
- Use `No Trade` when probability, confluence, or risk validation is not good enough.
- Use `no_trade_intelligence.suggested_action` and `next_review_condition` to guide the next review.
- Source selected strategy name/version from the strategy registry metadata.
