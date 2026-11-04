#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WIPE=false
case "${1:-}" in
    "") ;;
    -v|--wipe) WIPE=true ;;
    *) echo "usage: scripts/stop.sh [-v|--wipe]   (--wipe also deletes the local DB volume)" >&2; exit 1 ;;
esac

API_PATTERN="$ROOT/.venv/bin/uvicorn api.main:app"

if pgrep -f "$API_PATTERN" >/dev/null; then
    echo "==> Stopping API"
    pkill -TERM -f "$API_PATTERN" || true
    # Give uvicorn time to shut down gracefully before forcing it.
    for _ in {1..20}; do
        pgrep -f "$API_PATTERN" >/dev/null || break
        sleep 0.5
    done
    if pgrep -f "$API_PATTERN" >/dev/null; then
        echo "    API did not exit, killing it"
        pkill -KILL -f "$API_PATTERN" || true
    fi
else
    echo "==> API not running"
fi

if ! docker info >/dev/null 2>&1; then
    echo "==> Docker is not running, nothing else to stop"
    exit 0
fi

if $WIPE; then
    echo "==> Stopping local Postgres and deleting its data"
    docker compose down -v --remove-orphans
else
    echo "==> Stopping local Postgres (data kept; --wipe to delete it)"
    docker compose down --remove-orphans
fi
