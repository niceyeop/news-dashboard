#!/usr/bin/env bash
set -euo pipefail

: "${APP_DIR:?APP_DIR is required}"
: "${REPO_URL:?REPO_URL is required}"
BRANCH="${BRANCH:-main}"

if [ ! -d "$APP_DIR/.git" ]; then
  mkdir -p "$APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
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
sudo systemctl --no-pager --full status news-dashboard.service
