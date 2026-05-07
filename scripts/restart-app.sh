#!/bin/bash
# Restart only the FastAPI backend (uvicorn). Leaves docker services untouched.
# Use this after editing backend code; use scripts/start.sh for first-time/full start.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

echo "Stopping any existing uvicorn..."
# Match both `:app` and `:create_app --factory` invocations
pkill -f "uvicorn backend.app.main" 2>/dev/null || true
sleep 1

# Wait until port 8000 is actually free (pkill returns before the socket releases)
for _ in $(seq 1 10); do
    lsof -i :8000 -sTCP:LISTEN >/dev/null 2>&1 || break
    sleep 1
done

cd "$PROJECT_ROOT"

echo "Clearing __pycache__ to avoid stale bytecode..."
find backend -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
echo "Starting FastAPI on :8000 (--reload)..."
nohup python -m uvicorn backend.app.main:app --reload --port 8000 \
    > /tmp/resumehelper-fastapi.log 2>&1 &

for _ in $(seq 1 20); do
    if curl -sf http://localhost:8000/docs >/dev/null 2>&1; then
        echo "FastAPI is up."
        exit 0
    fi
    sleep 1
done

echo "WARN: FastAPI did not become ready in 20s. Check /tmp/resumehelper-fastapi.log"
exit 1
