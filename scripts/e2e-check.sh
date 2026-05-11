#!/usr/bin/env bash
# e2e-check.sh — run API smoke tests and optionally post results to a GitHub PR.
#
# Usage:
#   ./scripts/e2e-check.sh               # print results to stdout
#   ./scripts/e2e-check.sh --pr <number> # print + post as PR comment
#
# Requires: curl, jq (brew install jq)
# Server must be running: uvicorn backend.app.main:app --port 8000

set -euo pipefail

BASE_URL="${API_BASE_URL:-http://localhost:8000}"
PR_NUMBER=""
RESULTS=""
PASS=0
FAIL=0

while [[ $# -gt 0 ]]; do
  case $1 in
    --pr) PR_NUMBER="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# ── helpers ────────────────────────────────────────────────────────────────

check() {
  local label="$1" method="$2" path="$3" expected_status="$4"
  shift 4
  local extra_args=("$@")

  local http_code body
  body=$(curl -s -o /tmp/e2e_body.json -w "%{http_code}" \
    -X "$method" "${BASE_URL}${path}" "${extra_args[@]}" 2>/dev/null)
  http_code="$body"
  body=$(cat /tmp/e2e_body.json 2>/dev/null || echo "{}")

  local status_icon
  if [[ "$http_code" == "$expected_status" ]]; then
    status_icon="✅"
    ((PASS++))
  else
    status_icon="❌"
    ((FAIL++))
  fi

  local line="${status_icon} **${label}** \`${method} ${path}\` → HTTP ${http_code} (expected ${expected_status})"
  local detail
  detail=$(echo "$body" | python3 -m json.tool 2>/dev/null | head -20 || echo "$body")

  RESULTS+="${line}
\`\`\`json
${detail}
\`\`\`

"
  echo "${status_icon} ${label}: HTTP ${http_code}"
}

# ── tests ──────────────────────────────────────────────────────────────────

echo "Running e2e checks against ${BASE_URL} ..."
echo ""

check "Health check" \
  GET /api/health 200

check "Set baseline profile" \
  POST /api/profile 200 \
  -H "Content-Type: application/json" \
  -d '{"skills_text":"Python, FastAPI, PostgreSQL, REST APIs, Docker, 3 years backend experience"}'

check "Get baseline profile" \
  GET /api/profile 200

check "Evaluate JD (new)" \
  POST /api/evaluate 200 \
  -H "Content-Type: application/json" \
  -d '{"jd_text":"We are looking for a backend engineer with Python and FastAPI experience. PostgreSQL a plus."}'

check "Get history list" \
  GET /api/history 200

check "404 on unknown history item" \
  GET "/api/history/00000000-0000-0000-0000-000000000000" 404

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"

# ── post to PR if requested ────────────────────────────────────────────────

GITHUB_API_TOKEN="${GITHUB_PAT:-${GITHUB_TOKEN:-}}"

if [[ -n "$PR_NUMBER" && -n "$GITHUB_API_TOKEN" ]]; then
  REPO="jackylailai/resumeHelper"
  TIMESTAMP=$(date -u "+%Y-%m-%d %H:%M UTC")
  SUMMARY="${PASS} passed · ${FAIL} failed"
  if [[ "$FAIL" -eq 0 ]]; then
    HEADER="## E2E Results ✅ — ${SUMMARY} · ${TIMESTAMP}"
  else
    HEADER="## E2E Results ❌ — ${SUMMARY} · ${TIMESTAMP}"
  fi

  COMMENT_BODY="${HEADER}

${RESULTS}"

  PAYLOAD=$(python3 -c "import sys,json; print(json.dumps({'body': sys.argv[1]}))" "$COMMENT_BODY")

  RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer ${GITHUB_API_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${REPO}/issues/${PR_NUMBER}/comments" \
    -d "$PAYLOAD")

  COMMENT_URL=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('html_url','error'))" 2>/dev/null)
  echo "Posted to PR: ${COMMENT_URL}"
fi

# Exit non-zero if any check failed
[[ "$FAIL" -eq 0 ]]
