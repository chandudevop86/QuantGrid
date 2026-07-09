# Dhan Market Data Setup

Set the provider:

```env
QUANTGRID_MARKET_DATA_PROVIDER=dhan
QUANTGRID_BROKER_CLIENT_ID=...
QUANTGRID_BROKER_ACCESS_TOKEN=...
DHAN_SECURITY_ID_NIFTY=13
DHAN_MARKET_EXCHANGE_SEGMENT=IDX_I
DHAN_INSTRUMENT_TYPE=INDEX
```

Do not commit credentials. Keep broker tokens in environment variables or your deployment secret manager.

QuantGrid uses the official `dhanhq` Python package when it is installed. Dhan credentials still come only from environment variables.

The Dhan provider is fail-closed: if credentials, SDK import, quote data, or candle data are unavailable, live execution is blocked rather than falling back to Yahoo.

## Option-Chain/Data API Preflight

Profile login and option-chain access are separate checks. `/v2/profile` can pass while option-chain still fails because Dhan Data APIs / Option Chain are not enabled for the account, the server outbound IP is not whitelisted, or the configured client ID does not match the token account.

Use the broker diagnostic endpoint after saving credentials:

```bash
curl -H "Authorization: Bearer <admin-or-ops-token>" \
  "https://<domain>/api/broker/dhan/option-chain/status?symbol=NIFTY"
```

Expected healthy fields:

- `profile_connected=true`
- `option_chain_access=true`
- `data_api_connected=true`
- `expiry_available=true`

If `profile_connected=true` but `option_chain_access=false`, verify Dhan Data APIs / Option Chain entitlement, static outbound IP whitelisting, client ID/token account match, and then refresh the Dhan access token.
