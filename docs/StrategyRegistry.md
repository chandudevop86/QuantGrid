# Strategy Registry

Strategies are governed through `Backend/domain/engine/strategy_engine.py`.

Each registered strategy has:

- `name`
- `version`
- `enabled`
- `rollout_pct`
- `audit_trail`

The decision pipeline consumes registry metadata directly for strategy selection. It uses `name`, `version`, `enabled`, `rollout_pct`, and `supported_regimes` without executing strategy code during selection.

Disabled strategies and strategies with `rollout_pct` set to zero are ignored by the selector.
