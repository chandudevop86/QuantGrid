#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

ACTION="${1:-test}"
MODE="${2:-http}"
SITE_NAME="${SITE_NAME:-quantgrid}"
DOMAIN="${DOMAIN:-chandudevopai.shop}"
WWW_DOMAIN="${WWW_DOMAIN:-www.${DOMAIN}}"
CERT_NAME="${CERT_NAME:-${DOMAIN}}"

validate_hostname() {
  [[ "$1" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "Invalid hostname: $1" >&2; exit 2; }
}

render_config() {
  local source="$1" target="$2"
  validate_hostname "${DOMAIN}"
  validate_hostname "${WWW_DOMAIN}"
  validate_hostname "${CERT_NAME}"
  sed \
    -e "s/www\.chandudevopai\.shop/${WWW_DOMAIN}/g" \
    -e "s/chandudevopai\.shop/${DOMAIN}/g" \
    -e "s#/etc/letsencrypt/live/${DOMAIN}/#/etc/letsencrypt/live/${CERT_NAME}/#g" \
    "${source}" >"${target}"
}

case "${ACTION}" in
  install)
    if [[ "${MODE}" == "https" ]]; then
      SOURCE="${APP_DIR}/deploy/nginx/quantgrid.conf"
      CERT_DIR="/etc/letsencrypt/live/${CERT_NAME}"
      if [[ ! -r "${CERT_DIR}/fullchain.pem" || ! -r "${CERT_DIR}/privkey.pem" ]]; then
        cat >&2 <<EOF
TLS certificate files are missing for ${CERT_NAME}.

Bootstrap HTTP first, issue the certificate, then enable HTTPS:
  bash deploy/scripts/nginx.sh install http
  sudo certbot certonly --webroot -w /var/www/certbot \
    -d ${DOMAIN} -d ${WWW_DOMAIN}
  bash deploy/scripts/nginx.sh install https
EOF
        exit 1
      fi
    else
      SOURCE="${APP_DIR}/deploy/nginx/quantgrid-http.conf"
    fi
    require_file "${SOURCE}"
    TEMP_CONFIG="$(mktemp)"
    trap 'rm -f "${TEMP_CONFIG}"' EXIT
    render_config "${SOURCE}" "${TEMP_CONFIG}"
    run sudo mkdir -p /var/www/certbot
    run sudo install -m 0644 "${TEMP_CONFIG}" "/etc/nginx/sites-available/${SITE_NAME}"
    run sudo ln -sf "/etc/nginx/sites-available/${SITE_NAME}" "/etc/nginx/sites-enabled/${SITE_NAME}"
    if [[ -L /etc/nginx/sites-enabled/default ]]; then
      log "Disabling Ubuntu's default Nginx site to avoid duplicate default_server listeners"
      run sudo unlink /etc/nginx/sites-enabled/default
    fi
    run sudo nginx -t
    if sudo systemctl is-active --quiet nginx; then
      run sudo systemctl reload nginx
    else
      log "Nginx is stopped; starting it with the validated ${MODE} configuration"
      run sudo systemctl start nginx
    fi
    log "Installed Nginx config for ${DOMAIN} (${MODE})"
    ;;
  reload)
    run sudo nginx -t
    run sudo systemctl reload nginx
    ;;
  test)
    run sudo nginx -t
    ;;
  *)
    echo "Usage: $0 {install|reload|test} [http|https]" >&2
    exit 2
    ;;
esac
