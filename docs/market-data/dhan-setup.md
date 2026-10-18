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

Profile login and option-chain access are separate checks. `/v2/profile` may pass while Option Chain rejects the supplied credential pair. Follow Dhan's Data API response codes: `806` not subscribed, `807` expired token, `808` invalid client ID or access token, `809` invalid token, and `810` invalid client ID. Dhan documents static IP whitelisting for order placement APIs, not ordinary market-data requests.

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

If `profile_connected=true` but `option_chain_access=false`, follow the error code: for `808`, verify the current client ID and access token used by the **running QuantGrid API service** (profile success alone does not prove Data API authentication). For `806` with an active plan, ask Dhan support to check entitlement instead of buying another subscription. Refresh credentials only through authenticated Broker setup or the secret manager, without printing tokens. Keep live-money trading disabled. See [Dhan error codes](https://dhanhq.co/docs/v2/annexure/).
