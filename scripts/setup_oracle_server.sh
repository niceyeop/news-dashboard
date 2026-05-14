#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   sudo bash scripts/setup_oracle_server.sh <deploy_user> [app_dir]
# Example:
#   sudo bash scripts/setup_oracle_server.sh ubuntu /opt/news-dashboard

DEPLOY_USER="${1:-}"
APP_DIR="${2:-/opt/news-dashboard}"
SERVICE_NAME="news-dashboard.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
SUDOERS_PATH="/etc/sudoers.d/news-dashboard-deploy"

if [[ -z "$DEPLOY_USER" ]]; then
  echo "deploy_user is required"
  echo "usage: sudo bash scripts/setup_oracle_server.sh <deploy_user> [app_dir]"
  exit 1
fi

apt update
apt install -y git python3 python3-venv python3-pip

mkdir -p "$APP_DIR"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=News Dashboard (Streamlit)
After=network.target

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=-$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > "$SUDOERS_PATH" <<EOF
$DEPLOY_USER ALL=(root) NOPASSWD:/bin/systemctl daemon-reload,/bin/systemctl restart news-dashboard.service,/bin/systemctl --no-pager --full status news-dashboard.service
EOF

chmod 440 "$SUDOERS_PATH"
visudo -cf "$SUDOERS_PATH"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo "Setup complete"
echo "Next: create $APP_DIR/.env as $DEPLOY_USER and push to main."
