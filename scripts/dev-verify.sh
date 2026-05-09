#!/usr/bin/env bash
# Quick local sanity check for the running FastAPI app.
# Hits /api/health (DB + LLM config) and /api/debug/claude-cli-ping (real CLI
# spawn). Exits non-zero if either fails. Works against host or container
# modes — the URL is the same.
#
# Usage:
#   ./scripts/dev-verify.sh                 # localhost:8000
#   BASE_URL=http://x:8000 ./scripts/dev-verify.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }

echo "== /api/health =="
health=$(curl -sf -m 10 "$BASE_URL/api/health") || { red "health endpoint unreachable at $BASE_URL"; exit 1; }
echo "$health" | python3 -m json.tool

if ! echo "$health" | python3 -c "import sys, json; d=json.load(sys.stdin)['data']; sys.exit(0 if d['can_evaluate'] else 1)"; then
  red "health says can_evaluate=false — see next_actions above"
  exit 1
fi
green "health ok, can_evaluate=true"

echo
echo "== /api/debug/claude-cli-ping =="
ping=$(curl -sf -m 90 "$BASE_URL/api/debug/claude-cli-ping") || { red "ping endpoint unreachable (note: gated to non-prod)"; exit 1; }
echo "$ping" | python3 -m json.tool

if ! echo "$ping" | python3 -c "import sys, json; d=json.load(sys.stdin)['data']; sys.exit(0 if d.get('ok') else 1)"; then
  red "claude CLI ping returned ok=false — check stderr above and CLAUDE_CODE_OAUTH_TOKEN in .env"
  exit 1
fi
green "claude CLI ping ok"
