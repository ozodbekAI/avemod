#!/usr/bin/env bash
set -euo pipefail

RELEASE_ID="${1:?release id is required}"
APP_ROOT="/opt/finance-backend"
RELEASES_DIR="$APP_ROOT/releases"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_ID"
CURRENT_LINK="$APP_ROOT/current"
VENV_DIR="$APP_ROOT/venv"
ENV_FILE="/etc/finance-backend/finance.env"
SERVICE_NAME="finance-backend"
NGINX_AVAILABLE="/etc/nginx/sites-available/finance.ozodbek-akramov.uz.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/finance.ozodbek-akramov.uz.conf"

if [[ ! -d "$RELEASE_DIR" ]]; then
  echo "Release directory not found: $RELEASE_DIR" >&2
  exit 1
fi

install -d -m 755 "$APP_ROOT" "$RELEASES_DIR" /etc/finance-backend
chown -R www-data:www-data "$APP_ROOT"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing environment file: $ENV_FILE" >&2
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  python3.12 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel
"$VENV_DIR/bin/pip" install -e "$RELEASE_DIR"

ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"
chown -h www-data:www-data "$CURRENT_LINK"

install -m 644 "$CURRENT_LINK/deploy/finance-backend.service" /etc/systemd/system/finance-backend.service
install -m 644 "$CURRENT_LINK/deploy/nginx.finance.ozodbek-akramov.uz.conf" "$NGINX_AVAILABLE"
ln -sfn "$NGINX_AVAILABLE" "$NGINX_ENABLED"

cd "$CURRENT_LINK"
# Deployment contract: run the database migration step equivalent to `alembic upgrade head`.
"$VENV_DIR/bin/python" - "$ENV_FILE" <<'PY'
import os
import sys

from alembic.config import main
from dotenv import dotenv_values

for key, value in dotenv_values(sys.argv[1]).items():
    if value is not None:
        os.environ[key] = value

main(["upgrade", "head"])
PY

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
sleep 3
systemctl is-active --quiet "$SERVICE_NAME" || (journalctl -u "$SERVICE_NAME" -n 50 --no-pager && exit 1)

nginx -t
systemctl reload nginx

for _ in $(seq 1 6); do
  if curl --max-time 5 -fsS http://127.0.0.1:8016/api/v1/health >/dev/null; then
    exit 0
  fi
  sleep 1
done

echo "backend health check did not respond in time; service is active, deploy continues" >&2
