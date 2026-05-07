#!/bin/bash
# Start the full local stack: postgres + n8n (docker) + FastAPI (host).
# Idempotent — safe to re-run. Does NOT remove volumes.
# For app-only restarts (after editing backend code), use scripts/restart-app.sh.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

DATA_PATH="${RESUMEHELPER_DATA_PATH:-$HOME/resumeHelper_data}"
echo "Data directory: $DATA_PATH"
mkdir -p "$DATA_PATH"

cd "$PROJECT_ROOT"

echo "Starting docker services (postgres, n8n)..."
RESUMEHELPER_DATA_PATH="$DATA_PATH" docker-compose up -d

echo "Waiting for postgres to be ready..."
for _ in $(seq 1 30); do
    if docker exec resumehelper-postgres pg_isready -U postgres -d resume_helper >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

bash "$SCRIPT_DIR/restart-app.sh"

echo
docker-compose ps
echo
echo "FastAPI:    http://localhost:8000"
echo "Swagger:    http://localhost:8000/docs"
echo "n8n:        http://localhost:5678"
echo "Postgres:   localhost:5432"
