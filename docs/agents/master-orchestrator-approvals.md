# QuantGrid Master Agent: safe automation and owner approvals

**This is a design and initial policy implementation, not an active notification service or production automation.**

## Managed agents
Security, Network Reliability, Financial Risk, Market Research, SEBI Compliance, CI Bottleneck and Development agents.

## Policy
- Automatic in CI/staging: read-only monitoring, unit tests, static analysis, dependency scans, reports, and draft PR creation.
- Owner approval required: production deployment, PR merge, live trading enablement, risk/strategy changes, broker credentials, client access, firewall or regulatory policy changes.
- Prohibited through master agent: live order placement, withdrawals, audit disabling, bypassing security or risk controls, sharing client secrets.
- Unknown actions default to manual review. Missing or expired approvals mean no action.
- An approval is not an execution authorization; independent CI, Security, risk, broker, regulatory and change-management gates still apply.

## Approval request examples

**Security agent — production dependency patch**
Subject: [QuantGrid APPROVAL REQUIRED] Security patch production rollout
Issue: Vulnerable npm dependency; patch proposed and tested in PR.
Impact: New frontend build; possible temporary deployment interruption.
Options: Approve after all checks pass / Reject / Request staging evidence.
Rollback: Deploy last verified frontend release.

**Network agent — database scaling**
Subject: [QuantGrid APPROVAL REQUIRED] PostgreSQL connection-pool change
Issue: Sustained 90% pool saturation.
Impact: Restart and resource usage increase.
Options: Approve scheduled change / Reject / Request load test.
Rollback: Restore prior configuration.

**Financial agent — live-trading request**
Subject: [QuantGrid APPROVAL REQUIRED] Live trading pilot
Issue: Proposed capped pilot.
Impact: Potential real financial loss.
Options: Approve evaluation only / Reject / Request broker approval evidence.
Rollback: Keep live disabled and retain paper mode.
Note: Owner approval alone never activates trading.

**Compliance agent — client onboarding**
Subject: [QuantGrid APPROVAL REQUIRED] Multi-client onboarding
Issue: New broker/exchange and legal obligations.
Options: Approve compliance review / Reject / Request external counsel opinion.
No client access until external requirements are satisfied.

## Notification delivery design
- GitHub Issues and PR comments: tracking and auditable decision record.
- Email: use an authorized mail connector or SMTP/transactional provider; recipients and API keys must be stored as secrets, not committed.
- Phone: use an opted-in SMS/WhatsApp Business provider with approved templates and destination number stored securely.
- Email/SMS are alerts, not authorization channels by themselves. Approval must occur through an authenticated GitHub/environment protection or dedicated approval portal with identity, request ID, expiry and immutable audit.
- Use deduplication, retry with backoff, quiet-hours preference for noncritical events, delivery status, and escalation for critical incidents.
- Avoid sending broker tokens, client PII, order secrets or sensitive financial records in notifications.

## Next implementation requirements
Build a persistent approval request store, cryptographically bound approver identity, expiry and one-time tokens, GitHub issue integration, configured email/SMS provider, authenticated approval UI, workflow gating, audit logs and regression tests. Do not enable unattended production changes until end-to-end approval checks pass.
