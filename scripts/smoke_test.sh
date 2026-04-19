#!/usr/bin/env bash
# Smoke test for the alcohol label verifier.
#
# Local usage (boots a server on a throwaway port, runs the eval, tears down):
#     bash scripts/smoke_test.sh
#
# Deployed usage (skip local boot, hit the given URL):
#     SMOKE_BASE_URL=https://your-app.onrender.com bash scripts/smoke_test.sh

set -euo pipefail

BASE_URL="${SMOKE_BASE_URL:-}"
LOCAL_PORT="${SMOKE_LOCAL_PORT:-8765}"
LOCAL_MODE=false
SERVER_PID=""
SERVER_LOG="$(mktemp -t smoke-server.XXXXXX.log)"
EVAL_LOG="$(mktemp -t smoke-eval.XXXXXX.log)"

fail() {
  echo "[SMOKE FAIL] $*" >&2
  if [[ -s "$SERVER_LOG" ]]; then
    echo "----- server log (last 40 lines) -----" >&2
    tail -n 40 "$SERVER_LOG" >&2 || true
  fi
  exit 1
}

cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -f "$SERVER_LOG" "$EVAL_LOG"
}
trap cleanup EXIT

require() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

require python3
require curl

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -z "$BASE_URL" ]]; then
  LOCAL_MODE=true
  BASE_URL="http://127.0.0.1:${LOCAL_PORT}"
  require uvicorn
  echo "[smoke] booting local server on ${BASE_URL} ..."
  uvicorn app.main:app --host 127.0.0.1 --port "$LOCAL_PORT" >"$SERVER_LOG" 2>&1 &
  SERVER_PID=$!

  # Wait up to 90s for readiness (first boot warms PaddleOCR which is slow).
  for i in $(seq 1 90); do
    if curl -sf "${BASE_URL}/healthz" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  curl -sf "${BASE_URL}/healthz" >/dev/null 2>&1 \
    || fail "server on ${BASE_URL} did not become ready within 90s"
fi

# 1. Health check
echo "[smoke] GET ${BASE_URL}/healthz ..."
HEALTH_BODY="$(curl -sSf "${BASE_URL}/healthz")" \
  || fail "GET /healthz failed"
echo "$HEALTH_BODY" | grep -q '"status"' \
  || fail "/healthz body missing status field: ${HEALTH_BODY}"

# 2. Seeded sample submission through the demo path
echo "[smoke] POST ${BASE_URL}/demo/gs_001 ..."
DEMO_STATUS="$(curl -s -o /tmp/smoke-demo-body.html -w '%{http_code}' -X POST "${BASE_URL}/demo/gs_001")"
[[ "$DEMO_STATUS" == "200" ]] \
  || fail "POST /demo/gs_001 returned HTTP ${DEMO_STATUS}"
grep -q "Verification Results" /tmp/smoke-demo-body.html \
  || fail "POST /demo/gs_001 did not render a verdict"
rm -f /tmp/smoke-demo-body.html

# 3. Golden-set eval against the real verifier (runs in-process, no server needed)
echo "[smoke] running golden-set eval ..."
ALC_EVAL_TARGET="${ALC_EVAL_TARGET:-alc_label_verifier.adapter:target}" \
  python3 evals/run_golden_set.py >"$EVAL_LOG" 2>&1 || {
    tail -n 40 "$EVAL_LOG" >&2
    fail "golden-set eval did not exit cleanly"
  }

if $LOCAL_MODE; then
  echo "[smoke] local mode: all checks passed"
else
  echo "[smoke] deployed mode (${BASE_URL}): all checks passed"
fi

echo "[SMOKE PASS]"
