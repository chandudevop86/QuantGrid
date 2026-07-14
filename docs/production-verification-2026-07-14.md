# Production verification record — 2026-07-14

Status: **BLOCKED — not approved for production or live-money trading**

## Verification evidence

| Control | Result | Evidence / required action |
|---|---|---|
| Apex DNS | PASS | `chandudevopai.shop` resolved to `13.222.179.171`. |
| WWW DNS | FAIL | `www.chandudevopai.shop` returned NXDOMAIN. Create the intended A/ALIAS/CNAME record or remove `www` from the certificate and Nginx configuration. |
| HTTP reachability | WARNING | Port 80 returned `200 OK` from Nginx instead of redirecting to HTTPS. Deploy the hardened Nginx configuration. |
| HTTPS/TLS | FAIL | TCP port 443 was unreachable. Confirm AWS security-group ingress, certificate issuance, and the HTTPS Nginx site. |
| Public health check | FAIL | `http://chandudevopai.shop/health` returned the frontend SPA document, not backend health JSON. Deploy the updated Nginx route and verify `/health` before approval. |
| Monitoring alert | NOT VERIFIED | Trigger and record a synthetic availability alert plus one service/worker failure alert. Include timestamps and delivery destination without secrets. |
| Notification delivery | NOT VERIFIED | Telegram, Slack, and SMTP code paths are tested, but production delivery requires configured destinations and a received test notification. |
| Broker/API credential rotation | NOT VERIFIED | Rotation must be completed in the broker/provider account. Record only vault item/version, operator, and rotation time—never the token. |
| Staging restore drill | NOT VERIFIED | Requires a staging PostgreSQL URL and an encrypted backup archive. Record checksum, duration, migration status, and row-count checks. |
| Client UAT/sign-off | NOT COMPLETE | A client product owner and technical owner must complete `uat-acceptance-template.md`. |
| Live-money trading | BLOCKED | Repository production template sets `QUANTGRID_ENABLE_LIVE_TRADING=false`. Do not change it without a separately approved release. |

## Required server remediation

```bash
cd /root/QuantGrid
git pull

# Issue/renew the certificate after DNS is correct.
sudo certbot certonly --webroot -w /var/www/certbot \
  -d chandudevopai.shop -d www.chandudevopai.shop

DOMAIN=chandudevopai.shop \
WWW_DOMAIN=www.chandudevopai.shop \
CERT_NAME=chandudevopai.shop \
  bash deploy/scripts/nginx.sh install https

sudo nginx -t
curl -fsSI https://chandudevopai.shop/
curl -fsS https://chandudevopai.shop/health
```

AWS security-group ingress must allow TCP 443 from the intended public networks. Port 8000 must remain private.

## Credential rotation evidence

- Provider/broker:
- Vault item/version:
- Rotated by:
- Rotation time (IST):
- Old credential revoked: Yes / No
- Broker profile check passed: Yes / No
- Secret scanner passed after rotation: Yes / No

## Staging restore evidence

```bash
bash deploy/scripts/database-backup.sh backup
bash deploy/scripts/database-backup.sh verify backups/<archive>.dump
export RESTORE_DATABASE_URL='<staging URL from the secret manager>'
export ALLOW_DATABASE_RESTORE=YES
bash deploy/scripts/database-backup.sh restore backups/<archive>.dump
QUANTGRID_ENV_FILE=/path/to/staging-restore.env bash deploy/scripts/database.sh check
```

- Backup checksum:
- Restore target identifier (no credentials):
- Start/end time:
- Migration ledger verified:
- Critical row-count checks:
- Application smoke test:
- Operator/approver:

## Alert-delivery evidence

- Synthetic HTTPS alert triggered and received:
- Backend/worker alert triggered and received:
- QuantGrid application test notification received:
- Delivery channel and timestamp:
- Runbook link present in alert:

## Final release gate

Release remains blocked until every FAIL, NOT VERIFIED, and NOT COMPLETE entry above has evidence and named approval. Live-money trading remains disabled even after ordinary production approval; it requires a separate real-money trading authorization.
