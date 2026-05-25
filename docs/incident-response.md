# Incident Response

## Severity

- SEV1: trading safety, auth bypass, data loss, production outage.
- SEV2: major workflow degraded, no workaround.
- SEV3: partial degradation with workaround.

## Process

1. Declare incident and owner.
2. Stabilize: disable risky actions, pause deployments, preserve logs.
3. Assess blast radius.
4. Roll back if the latest release is implicated.
5. Communicate status and next update time.
6. Resolve.
7. Write post-incident review within two business days.

## Trading Safety Actions

- Keep `QUANTGRID_ENABLE_LIVE_TRADING=false` unless explicitly approved.
- Prefer rejecting execution over accepting uncertain market data.
- Preserve audit logs.
