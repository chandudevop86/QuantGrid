# QuantGrid Workspace V3 — frontend redesign

## Scope

A unified, responsive visual system across the existing QuantGrid frontend; **not a trading-engine rewrite**. No routes, broker APIs, account roles, entitlements, risk limits, subscription gates or trading-mode semantics are bypassed.

### Implemented

- **Global shell:** redesigned 240px navigation, desktop research-context rail, sticky product header, denser typography, teal/navy palette, consistent card/table/form/status visual system
- **Mobile/tablet:** accessible slide-out navigation (rather than a truncated bottom-only menu), visible menu action at phone widths, backdrop dismissal and Escape support
- **Keyboard search:** Ctrl/Cmd+K opens an accessible navigation dialog. Results are restricted by role *and* subscription entitlements; arrows/Enter navigate; Escape dismisses
- **Dashboard:** instrument heading follows the selected market instead of always claiming NIFTY 50; status dot is muted when the exchange session is not verified open
- **Honest market context:** removes hard-coded index numbers, unverified market-breadth commentary and fabricated exposure figures previously rendered in the right rail; source timestamps, feed/socket state and missing-data warnings are displayed instead
- **Consistent existing modules:** styles for market charts, options, institutional flow, quality-growth investment screens, positions, risk, analysis and management pages share V3 design tokens; original page interactions remain unchanged
- **Safety/accessibility:** no live order submission added, no implicit live-trading activation, keyboard focus states, reduced-motion support, scrollable tables and source-conscious missing states

### Implementation pattern

Original `src/index.css` has a legacy 4k+ line ruleset, so V3 is a **separate additive stylesheet** `src/workspace-v3.css` imported **after** the existing CSS in `src/main.tsx`. Existing page functionality and targeted CSS remain intact. A future cleanup may consolidate unused legacy selectors after cross-device visual regression testing.

Changes are scoped to layout, navigation, shared CSS, search palette, truthful display labels, and tests. No API contracts are modified. Static checks protect against reintroducing sample market figures and ensure route/entitlement filtering remains in place.

### QA / release

Run at this PR's exact head:
```bash
cd apps/frontend
npm ci
npm run build
npm run test -- --run
cd ../..
PYTHONPATH=services/trading-service:services/tests python -m pytest -q services/tests/test_frontend_workspace_v3.py services/tests/test_frontend_navigation_labels.py services/tests/test_frontend_live_warning.py
```

Verify manually at 1440px, 1280px, 1024px, 768px and 375px. Check login, portfolio/research/market screens, drawer backdrop, Ctrl/Cmd+K, status and API outage conditions, trade entry constraints, and keyboard focus. Confirm a trade can never be triggered from the global search or context rail.

**Production release requires independent review and explicit approval**. Existing production server checkout was previously behind GitHub; do not use `git reset --hard`, remove local reconciliation state, or force a deployment. Roll back by reverting this PR through the normal gated deployment workflow.
