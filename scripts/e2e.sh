#!/usr/bin/env bash
# Run the Playwright E2E suite locally.
#
# Usage:
#   scripts/e2e.sh                  # full suite
#   scripts/e2e.sh -k pasted_jd     # forwards args to pytest
#
# The suite spins its OWN ephemeral postgres (via testcontainers) and its
# OWN uvicorn process. The dev `resume_helper` DB is NEVER touched. The
# only prerequisite is a working Docker daemon (testcontainers needs it).

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
if ! ls "$HOME/Library/Caches/ms-playwright/chromium-"* >/dev/null 2>&1 \
   && ! ls "$HOME/.cache/ms-playwright/chromium-"* >/dev/null 2>&1; then
    echo "installing chromium..."
    "$VENV/bin/python" -m playwright install chromium
fi

# DATABASE_URL is intentionally NOT exported — testcontainers picks a
# random port for its own postgres, and conftest forces uvicorn to use it.
"$VENV/bin/python" -m pytest tools/e2e/tests/ "$@"
