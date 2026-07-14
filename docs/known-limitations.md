# Known limitations

- Production acceptance is paper-mode only. Live trading remains disabled until separately approved.
- Billing/payment processing is not connected; plan selection does not charge or auto-activate a paid subscription.
- External market and option-chain providers can throttle, delay, or omit data. The UI must show freshness and fallback status.
- Dhan option-chain access depends on Data API entitlement, valid credentials, and required IP allowlisting.
- Market decisions are probabilistic decision support, not investment advice or guaranteed outcomes.
- RPO/RTO targets are provisional until a timed restore drill is recorded in the target production environment.
- TLS, DNS, cloud monitoring, notification delivery, and third-party credential rotation require environment-owner evidence; repository tests cannot prove them.
- Advanced pages are retained for entitled users and may require wider desktop layouts; the primary dashboard remains the simplified mobile-first surface.
