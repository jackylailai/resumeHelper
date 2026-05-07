#!/bin/bash
# Restart only the FastAPI backend (uvicorn). Leaves docker services untouched.
# Use this after editing backend code; use scripts/start.sh for first-time/full start.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

echo "Stopping any existing uvicorn..."
pkill -f "uvicorn backend.app.main:app" 2>/dev/null || true
sleep 1

cd "$PROJECT_ROOT"
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
