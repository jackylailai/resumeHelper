#!/usr/bin/env bash
# Run the Playwright E2E suite locally.
#
# Usage:
#   scripts/e2e.sh                  # full suite
#   scripts/e2e.sh -k pasted_jd     # forwards args to pytest
#
# Prereqs: docker compose's postgres up (scripts/start.sh or compose up -d).
# This script will spawn its own uvicorn; it expects port 8001 to be free.

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
cd "$PROJECT_ROOT"

VENV="${PROJECT_ROOT}/.venv"
if [ ! -d "$VENV" ]; then
    echo "no .venv — run scripts/test.sh once to bootstrap"
    exit 1
fi

# Install Playwright + Chromium on first run.
if ! "$VENV/bin/python" -c "import playwright" 2>/dev/null; then
    echo "installing playwright + pytest-playwright into .venv..."
    "$VENV/bin/pip" install playwright pytest-playwright
fi
if [ ! -d "$HOME/Library/Caches/ms-playwright/chromium-"* ] 2>/dev/null \
   && [ ! -d "$HOME/.cache/ms-playwright/chromium-"* ] 2>/dev/null; then
    echo "installing chromium..."
    "$VENV/bin/python" -m playwright install chromium
fi

export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/resume_helper}"
export LLM_BACKEND=fake
export E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:8001}"

"$VENV/bin/python" -m alembic -c backend/alembic.ini upgrade head >/dev/null

"$VENV/bin/python" -m pytest tools/e2e/tests/ "$@"
