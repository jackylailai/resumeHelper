#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${RESUMEHELPER_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
LOG_DIR="${RESUMEHELPER_LOG_DIR:-$ROOT_DIR/backend/storage/logs}"
KEYWORD="${RESUMEHELPER_SCRAPE_KEYWORD:-backend engineer}"
SOURCE="${RESUMEHELPER_SCRAPE_SOURCE:-all}"
LIMIT="${RESUMEHELPER_SCRAPE_LIMIT:-25}"
EVALUATE_LIMIT="${RESUMEHELPER_EVALUATE_LIMIT:-100}"
PROFILE_ID="${RESUMEHELPER_PROFILE_ID:-}"
NO_TAILOR="${RESUMEHELPER_NO_TAILOR:-0}"
QUIET="${RESUMEHELPER_QUIET:-0}"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily-scrape-$(date +%Y%m%d).log"

cd "$ROOT_DIR"
{
  echo "[$(date -Is)] scrape start source=$SOURCE keyword=$KEYWORD limit=$LIMIT"
  args=(
    -m backend.app.cli scrape
    --source "$SOURCE"
    --keyword "$KEYWORD"
    --limit "$LIMIT"
    --evaluate
    --evaluate-limit "$EVALUATE_LIMIT"
  )
  if [[ -n "$PROFILE_ID" ]]; then
    args+=(--profile-id "$PROFILE_ID")
  fi
  if [[ "$NO_TAILOR" == "1" ]]; then
    args+=(--no-tailor)
  fi
  if [[ "$QUIET" == "1" ]]; then
    args+=(--quiet)
  fi
  python "${args[@]}"
  echo "[$(date -Is)] scrape done"
} >> "$LOG_FILE" 2>&1
