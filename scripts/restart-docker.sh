#!/usr/bin/env bash
# Force-rebuild the FastAPI image with --no-cache and restart the app container.
# Use this when you suspect cached/stale code is running.
#
# Usage:
#   ./scripts/restart-docker.sh           # rebuild + restart app only (postgres stays up)
#   ./scripts/restart-docker.sh --full    # also bring up postgres first

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
cd "$PROJECT_ROOT"

COMPOSE=(docker-compose -f docker-compose.yml -f docker-compose.app.yml)

# Free port 8000 from any lingering host uvicorn (covers `:app` and `:create_app --factory` patterns)
echo "Stopping host uvicorn (if any)..."
pkill -f "uvicorn backend.app.main" 2>/dev/null || true
sleep 1

if [[ "${1:-}" == "--full" ]]; then
  DATA_PATH="${RESUMEHELPER_DATA_PATH:-$HOME/resumeHelper_data}"
  mkdir -p "$DATA_PATH"
  echo "Bringing up postgres..."
  RESUMEHELPER_DATA_PATH="$DATA_PATH" "${COMPOSE[@]}" up -d postgres

  echo "Waiting for postgres..."
  for _ in $(seq 1 30); do
    if docker exec resumehelper-postgres pg_isready -U postgres -d resume_helper >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

echo "Stopping + removing existing app container..."
"${COMPOSE[@]}" rm -sf app 2>/dev/null || true

echo "Building app image (--no-cache)..."
"${COMPOSE[@]}" build --no-cache app

echo "Starting app container..."
"${COMPOSE[@]}" up -d --force-recreate app

echo "Waiting for FastAPI..."
for _ in $(seq 1 40); do
  if curl -sf http://localhost:8000/docs >/dev/null 2>&1; then
    echo "FastAPI is up — image built at $(docker inspect -f '{{.Created}}' resumehelper-app 2>/dev/null || echo unknown)"
    "${COMPOSE[@]}" ps app
    exit 0
  fi
  sleep 1
done

echo "WARN: FastAPI did not respond in 40s. Recent logs:"
"${COMPOSE[@]}" logs --tail=80 app
exit 1
