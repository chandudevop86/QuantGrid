#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer as root on the QuantGrid EC2 host." >&2
    exit 1
fi

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
test -f services/trading-service/Backend/application/options/auto_paper_execution.py
test -x /root/venv/bin/python
bash -n scripts/install_option_paper_watchdog.sh
/root/venv/bin/python -m py_compile \
    services/trading-service/Backend/application/options/auto_paper_execution.py \
    services/trading-service/Backend/application/options/paper_order_ledger.py \
    services/trading-service/Backend/infrastructure/market_data/dhan_option_execution.py

install -d -m 0700 services/trading-service/Backend/data /etc/quantgrid
install -d -m 0755 /etc/systemd/system/quantgrid-worker.service.d
cat > /etc/quantgrid/auto-option-paper.env <<'ENV'
QUANTGRID_AUTO_PAPER_ENABLED=true
QUANTGRID_AUTO_OPTION_PAPER_CANDIDATES=false
QUANTGRID_PAPER_RECONCILIATION_ENABLED=true
ENV
chmod 0600 /etc/quantgrid/auto-option-paper.env
cat > /etc/systemd/system/quantgrid-worker.service.d/auto-option-paper.conf <<'UNIT'
[Service]
EnvironmentFile=/etc/quantgrid/auto-option-paper.env
UNIT

install -m 0644 deploy/systemd/quantgrid-host-watchdog.service /etc/systemd/system/
install -m 0644 deploy/systemd/quantgrid-host-watchdog.timer /etc/systemd/system/
systemctl daemon-reload
systemctl restart quantgrid-backend quantgrid-worker
systemctl is-active quantgrid-backend quantgrid-worker
systemctl enable --now quantgrid-host-watchdog.timer
watchdog_result=0
systemctl start quantgrid-host-watchdog.service || watchdog_result=$?
systemctl list-timers quantgrid-host-watchdog.timer --no-pager
journalctl -u quantgrid-host-watchdog.service -n 5 --no-pager
journalctl -u quantgrid-worker --since "2 minutes ago" --no-pager -n 50
exit "$watchdog_result"
