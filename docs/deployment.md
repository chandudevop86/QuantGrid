# Deployment Guide

## Local Setup

```bash
python -m pip install -r services/trading-service/requirements.txt
cd apps/frontend && npm ci && npm run build
cd ../..
uvicorn Backend.presentation.api.main:app --app-dir services/trading-service --reload --port 8000
```

## Staging Setup

- Use Postgres, not SQLite.
- Set `QUANTGRID_ENV=staging`.
- Set `QUANTGRID_AUTH_SECRET` from a secret manager.
- Set `CORS_ALLOWED_ORIGINS` to the staging frontend origin.
- Keep `QUANTGRID_ENABLE_LIVE_TRADING=false`.

## Production Setup

- Use Postgres with persistent backups.
- Set `QUANTGRID_ENV=production`.
- Set `DATABASE_URL=postgresql+psycopg://...`.
- Set `QUANTGRID_AUTH_SECRET` to a strong secret.
- Set explicit `CORS_ALLOWED_ORIGINS`.
- Set `QUANTGRID_FORCE_HTTPS=true` when the API is behind the HTTPS Nginx proxy.
- Set frontend API variables to HTTPS URLs only, for example `VITE_API_URL=https://chandudevopai.shop/api`.
- Keep live trading disabled unless broker execution has been formally approved.

## Terraform AWS 3-Tier

The AWS infrastructure baseline lives in `infra/terraform/aws` and models:

`ALB public tier -> EC2 app private tier -> RDS Postgres / ElastiCache Redis data tier`

```bash
cd infra/terraform/aws
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt -check
terraform validate
terraform plan -var-file=terraform.tfvars
```

Do not commit `terraform.tfvars`. Supply `db_password`, AMI IDs, and environment-specific values through CI/CD secrets or a secure Terraform workspace.

## Systemd

```bash
bash deploy/scripts/backend.sh install
bash deploy/scripts/scheduler.sh install
sudo systemctl status quantgrid-backend --no-pager
sudo systemctl status quantgrid-worker --no-pager
sudo journalctl -u quantgrid-backend -n 200 --no-pager
```

## Nginx

```bash
bash deploy/scripts/frontend.sh deploy
bash deploy/scripts/production_frontend.sh stop-vite
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
bash deploy/scripts/nginx.sh install http
sudo certbot certonly --webroot -w /var/www/certbot -d your-domain.example -d www.your-domain.example
bash deploy/scripts/nginx.sh install https
sudo nginx -t
sudo systemctl reload nginx
bash deploy/scripts/production_frontend.sh check
```

For a client-owned hostname, render the checked configuration during installation:

```bash
DOMAIN=trade.example.com WWW_DOMAIN=www.trade.example.com CERT_NAME=trade.example.com \
  bash deploy/scripts/nginx.sh install https
```

The installer accepts hostname characters only, renders to a temporary file, validates with `nginx -t`, and reloads only after validation. Unknown HTTP hosts are rejected instead of being reflected into redirects.
It also disables Ubuntu's `/etc/nginx/sites-enabled/default` symlink when present, because QuantGrid owns the hardened default listeners and Nginx otherwise rejects the duplicate `default_server` declaration.

Verify certificate renewal and expiry monitoring during every production handover:

```bash
sudo certbot renew --dry-run
sudo systemctl status certbot.timer --no-pager
openssl s_client -connect trade.example.com:443 -servername trade.example.com </dev/null 2>/dev/null \
  | openssl x509 -noout -dates -issuer -subject
```

Alert before the certificate has fewer than 30 days remaining. Record the renewal dry-run and alert-delivery evidence in the release record.

The HTTPS config redirects all HTTP traffic to HTTPS after ACME challenges and sets HSTS, X-Frame-Options,
X-Content-Type-Options, and Referrer-Policy headers. Production browsers should show a secure lock icon.
Do not point a production browser session at `http://<server-ip>:8000`; HTTPS frontends cannot call HTTP APIs without
being blocked as mixed content.
Do not run Vite (`npm run dev`) as the public production frontend. Production must serve the built `apps/frontend/dist`
bundle from Nginx at `/var/www/quantgrid`.

## Database Check

```bash
cd /root/QuantGrid
bash deploy/scripts/database.sh check
```

`check` validates security configuration, initializes the existing trading-store schemas, tests connectivity, and prints
a password-masked database URL. `init` is an explicit alias for the same idempotent operation. The deployment scripts
run this shared database/schema check before backend or worker restart. Use `postgres.sh` only for Postgres container
start and status operations.

## Automated Deploy Scripts

```bash
DRY_RUN=1 bash deploy/scripts/deploy.sh
bash deploy/scripts/deploy.sh
bash deploy/scripts/restart.sh
bash deploy/scripts/logs.sh backend
bash deploy/scripts/logs.sh scheduler
```

`deploy/scripts/common.sh` centralizes paths, database checks, health checks, and dry-run behavior. Keep live trading disabled by default; these scripts do not enable broker-live mode.
Health checks wait up to 60 seconds by default (`HEALTH_RETRIES=30`, `HEALTH_SLEEP_SECONDS=2`) and print backend
`systemctl status` plus recent journal logs if port `8000` never becomes ready.

## Smoke Tests

```bash
bash scripts/jenkins/smoke_test.sh https://your-domain.example/api
```

## Rollback

```bash
bash scripts/jenkins/rollback.sh v0.1.0 production
```
