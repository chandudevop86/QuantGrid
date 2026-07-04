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

## Operating Rules

- Block signals when data is stale.
- Prefer No Trade when directional factors conflict.
- Keep live trading disabled unless all live safety gates are explicitly configured.
- Treat elevated VIX, expiry risk, and low liquidity as quality reducers or blockers.
