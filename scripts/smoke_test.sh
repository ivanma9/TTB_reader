#!/usr/bin/env bash
# Smoke test for the alcohol label verifier.
#
# Local usage (boots a server on a throwaway port, runs the eval, tears down):
#     bash scripts/smoke_test.sh
#
# Deployed usage (skip local boot, hit the given URL):
#     SMOKE_BASE_URL=https://your-app.up.railway.app bash scripts/smoke_test.sh

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

# 2. Queue flow: landing → item detail → verify → action
echo "[smoke] GET ${BASE_URL}/ (queue landing) ..."
curl -fsS "${BASE_URL}/" | grep -q "Review Queue" \
  || fail "queue landing did not render"

echo "[smoke] GET ${BASE_URL}/queue/gs_001 ..."
curl -fsS "${BASE_URL}/queue/gs_001" | grep -q "COLA-2026-0412-001" \
  || fail "queue item detail did not render"

echo "[smoke] POST ${BASE_URL}/queue/gs_001/verify ..."
VERIFY_BODY="$(mktemp -t smoke-verify.XXXXXX.html)"
VERIFY_STATUS="$(curl -s -o "$VERIFY_BODY" -w '%{http_code}' -X POST "${BASE_URL}/queue/gs_001/verify")"
[[ "$VERIFY_STATUS" == "200" ]] \
  || { rm -f "$VERIFY_BODY"; fail "POST /queue/gs_001/verify returned HTTP ${VERIFY_STATUS}"; }
grep -q "Verification Results" "$VERIFY_BODY" \
  || { rm -f "$VERIFY_BODY"; fail "POST /queue/gs_001/verify did not render a verdict"; }
rm -f "$VERIFY_BODY"

echo "[smoke] POST ${BASE_URL}/queue/gs_001/action ..."
ACTION_STATUS="$(curl -s -o /dev/null -w '%{http_code}' -X POST \
  -d "action=approved" "${BASE_URL}/queue/gs_001/action")"
[[ "$ACTION_STATUS" == "303" ]] \
  || fail "POST /queue/gs_001/action returned HTTP ${ACTION_STATUS} (expected 303)"

echo "[smoke] GET ${BASE_URL}/test ..."
curl -fsS "${BASE_URL}/test" | grep -q "Test a label" \
  || fail "/test did not render"

# 3. Golden-set eval against the real verifier (runs in-process, no server needed).
#    Only in local mode — when SMOKE_BASE_URL is set, POST /queue/gs_001/verify
#    already exercised the deployed verifier, and the local Python env may not
#    have paddleocr installed.
if $LOCAL_MODE; then
  echo "[smoke] running golden-set eval ..."
  ALC_EVAL_TARGET="${ALC_EVAL_TARGET:-alc_label_verifier.adapter:target}" \
    python3 evals/run_golden_set.py >"$EVAL_LOG" 2>&1 || {
      tail -n 40 "$EVAL_LOG" >&2
      fail "golden-set eval did not exit cleanly"
    }
  echo "[smoke] local mode: all checks passed"
else
  echo "[smoke] deployed mode (${BASE_URL}): web checks passed (eval skipped; run locally with no SMOKE_BASE_URL)"
fi

echo "[SMOKE PASS]"
