#!/usr/bin/env bash
# Start the Discord monitor. Run from anywhere.
# Usage: ./start.sh [--reply] [--interval 30] [--channel CHANNEL_ID]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Activate venv if present; otherwise use system Python
if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
    source "$REPO_ROOT/.venv/bin/activate"
fi

# Load project .env for ANTHROPIC_API_KEY (if present, never committed)
if [[ -f "$REPO_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +a
fi

exec python3 "$SCRIPT_DIR/monitor.py" "$@"
