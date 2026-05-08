#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SERVICE_USER="${SERVICE_USER:-$(id -un)}"
SERVICE_GROUP="${SERVICE_GROUP:-$(id -gn)}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo, for example:" >&2
  echo "sudo SERVICE_USER=$SERVICE_USER SERVICE_GROUP=$SERVICE_GROUP APP_DIR=$APP_DIR $0" >&2
  exit 1
fi

install -m 0755 "$APP_DIR/scripts/run_dashboard.sh" "$APP_DIR/scripts/run_dashboard.sh"
install -m 0755 "$APP_DIR/scripts/run_agent.sh" "$APP_DIR/scripts/run_agent.sh"
install -d -m 0755 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$APP_DIR/logs"

sed \
  -e "s|__APP_DIR__|$APP_DIR|g" \
  -e "s|__SERVICE_USER__|$SERVICE_USER|g" \
  -e "s|__SERVICE_GROUP__|$SERVICE_GROUP|g" \
  "$APP_DIR/deploy/systemd/sangahub-stt-dashboard.service" \
  > "$SYSTEMD_DIR/sangahub-stt-dashboard.service"

sed \
  -e "s|__APP_DIR__|$APP_DIR|g" \
  -e "s|__SERVICE_USER__|$SERVICE_USER|g" \
  -e "s|__SERVICE_GROUP__|$SERVICE_GROUP|g" \
  "$APP_DIR/deploy/systemd/sangahub-stt-agent.service" \
  > "$SYSTEMD_DIR/sangahub-stt-agent.service"

systemctl daemon-reload
systemctl enable sangahub-stt-dashboard.service sangahub-stt-agent.service

echo "Installed and enabled:"
echo "  sangahub-stt-dashboard.service"
echo "  sangahub-stt-agent.service"
echo
echo "Start them with:"
echo "  sudo systemctl start sangahub-stt-dashboard sangahub-stt-agent"
