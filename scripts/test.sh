#!/usr/bin/env bash
# test.sh — run the test suite under Python 3.11+ in a project-local venv.
#
# Why this exists: after #34 the codebase requires Python 3.11 (datetime.UTC,
# PEP 604 unions inside SQLAlchemy Mapped[...]). Most maintainers have an
# older default `python` (Anaconda 3.9, system 3.9 etc.); this script
# bootstraps a 3.11 venv at .venv/ so `./scripts/test.sh` just works.
#
# Usage:
#   ./scripts/test.sh                    # run unit + v2 integration tests
#   ./scripts/test.sh -k some_test       # forwards args to pytest
#   ./scripts/test.sh --recreate         # blow away .venv and rebuild
#
# Requires:
#   - python3.11 (or newer) on PATH. On macOS: `brew install python@3.11`.
#   - Docker running (testcontainers spawns Postgres for integration tests).

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

VENV_DIR=".venv"
MIN_MAJOR=3
MIN_MINOR=11

# ── arg parsing ────────────────────────────────────────────────────────────
RECREATE=0
PYTEST_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --recreate) RECREATE=1 ;;
    *) PYTEST_ARGS+=("$arg") ;;
  esac
done

# ── locate a usable Python 3.11+ ───────────────────────────────────────────
find_python() {
  for candidate in python3.13 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$(command -v "$candidate")"
      return 0
    fi
  done
  return 1
}

PY_BIN="${PY_BIN:-$(find_python || true)}"
if [[ -z "$PY_BIN" ]]; then
  cat >&2 <<'EOF'
error: no python3.11+ on PATH.
On macOS:   brew install python@3.11
On Linux:   apt-get install python3.11
Or set PY_BIN=/path/to/python3.11 before running this script.
EOF
  exit 1
fi

PY_VER="$("$PY_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="${PY_VER%%.*}"
PY_MINOR="${PY_VER##*.}"
if (( PY_MAJOR < MIN_MAJOR )) || { (( PY_MAJOR == MIN_MAJOR )) && (( PY_MINOR < MIN_MINOR )); }; then
  echo "error: $PY_BIN is Python $PY_VER but >=${MIN_MAJOR}.${MIN_MINOR} is required" >&2
  exit 1
fi

# ── venv: create or reuse ─────────────────────────────────────────────────
needs_create=0
if [[ ! -d "$VENV_DIR" ]]; then
  needs_create=1
elif [[ ! -x "$VENV_DIR/bin/python" ]]; then
  needs_create=1
else
  existing_ver="$("$VENV_DIR/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")"
  existing_major="${existing_ver%%.*}"
  existing_minor="${existing_ver##*.}"
  if (( existing_major < MIN_MAJOR )) || { (( existing_major == MIN_MAJOR )) && (( existing_minor < MIN_MINOR )); }; then
    echo "info: existing $VENV_DIR is Python $existing_ver — recreating with $PY_VER" >&2
    needs_create=1
  fi
fi

if (( RECREATE )); then
  needs_create=1
fi

if (( needs_create )); then
  rm -rf "$VENV_DIR"
  "$PY_BIN" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --quiet --upgrade pip
  "$VENV_DIR/bin/pip" install --quiet -r backend/requirements.txt
fi

# ── run tests ─────────────────────────────────────────────────────────────
exec "$VENV_DIR/bin/python" -m pytest \
  backend/tests/unit/ backend/tests/integration/v2/ \
  ${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"}
