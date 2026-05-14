#!/usr/bin/env bash
set -euo pipefail

: "${APP_DIR:?APP_DIR is required}"
: "${REPO_URL:?REPO_URL is required}"
BRANCH="${BRANCH:-main}"

if [ ! -d "$APP_DIR/.git" ]; then
  BACKUP_DIR=""
  if [ -d "$APP_DIR" ] && [ "$(ls -A "$APP_DIR" 2>/dev/null)" ]; then
    BACKUP_DIR="${APP_DIR}_backup_$(date +%Y%m%d%H%M%S)"
    mv "$APP_DIR" "$BACKUP_DIR"
  fi
  mkdir -p "$APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
  if [ -n "$BACKUP_DIR" ] && [ -f "$BACKUP_DIR/.env" ] && [ ! -f "$APP_DIR/.env" ]; then
    cp "$BACKUP_DIR/.env" "$APP_DIR/.env"
  fi
fi

cd "$APP_DIR"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

sudo systemctl daemon-reload
sudo systemctl restart news-dashboard.service
if ! sudo systemctl --no-pager --full status news-dashboard.service; then
  sudo journalctl -u news-dashboard.service -n 120 --no-pager || true
  exit 1
fi
