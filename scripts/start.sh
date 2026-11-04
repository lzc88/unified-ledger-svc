#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export APP_ENV="${APP_ENV:-local}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

command -v uv >/dev/null || { echo "uv not found (brew install uv)" >&2; exit 1; }

if pgrep -f "$ROOT/.venv/bin/uvicorn api.main:app" >/dev/null; then
    echo "API is already running (scripts/stop.sh to stop it)" >&2
    exit 1
fi
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $PORT is already in use (set PORT to use another)" >&2
    exit 1
fi

echo "==> Syncing dependencies"
uv sync

if [[ "$APP_ENV" == "local" ]]; then
    docker info >/dev/null 2>&1 || { echo "Docker is not running" >&2; exit 1; }
    echo "==> Starting local Postgres"
    docker compose up -d --wait
fi

echo "==> Applying migrations (APP_ENV=$APP_ENV)"
.venv/bin/alembic upgrade head

echo "==> Starting API on http://$HOST:$PORT (docs at /docs)"
# Absolute path so scripts/stop.sh can find this process.
exec "$ROOT/.venv/bin/uvicorn" api.main:app --host "$HOST" --port "$PORT" "$@"
