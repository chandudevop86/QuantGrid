# Strategy Registry

Strategies are governed through `Backend/domain/engine/strategy_engine.py`.

Each registered strategy has:

- `name`
- `version`
- `enabled`
- `rollout_pct`
- `audit_trail`

The decision pipeline adds a deterministic strategy selection scorecard so the dashboard can show the selected strategy and why alternatives lost.

