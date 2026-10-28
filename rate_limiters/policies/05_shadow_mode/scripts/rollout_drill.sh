#!/usr/bin/env bash
# Rollout Drill: Demonstrates safe shadow -> enforce transition with ZERO code changes.
# Usage:
#   make up P=shadow-mode
#   ./rate_limiters/policies/05_shadow_mode/scripts/rollout_drill.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8205}"
IDENTITY="user:rollout_client"

echo "=========================================================="
echo " ROLLOUT DRILL: Safe Limit Rollout via Shadow Mode"
echo " Base URL: ${BASE_URL}"
echo "=========================================================="

echo -e "\n--- STEP 1: Verify Initial Operating Mode ---"
curl -s "${BASE_URL}/admin/mode" | jq .

echo -e "\n--- STEP 2: Week 1 & 2 (Shadow Mode Active) ---"
echo "Sending rapid burst of 7 requests to /demo/dynamic..."
for i in {1..7}; do
  echo -n "Request $i: "
  curl -s -i -H "X-User-Id: ${IDENTITY}" "${BASE_URL}/demo/dynamic" | grep -E "(HTTP/|x-ratelimit-action|x-ratelimit-would-block)" || true
done
echo "Result: Client is NEVER interrupted (all 200 OK), but ops team observes would-be denials!"

echo -e "\n--- STEP 3: Flip Mode from Shadow to Enforce (NO CODE CHANGE / NO RESTART) ---"
curl -s -X POST "${BASE_URL}/admin/mode?mode=enforce" | jq .

echo -e "\n--- STEP 4: Week 3 (Enforce Mode Active) ---"
echo "Sending rapid burst to /demo/dynamic..."
for i in {1..7}; do
  echo -n "Request $i: "
  curl -s -i -H "X-User-Id: ${IDENTITY}" "${BASE_URL}/demo/dynamic" | grep -E "(HTTP/|x-ratelimit-action|retry-after)" || true
done
echo "Result: Over-quota traffic is now actively blocked with 429 Too Many Requests!"

echo -e "\n--- STEP 5: Allowlist Verification ---"
echo "Sending requests as allowlisted internal user (user:admin)..."
for i in {1..3}; do
  echo -n "Admin Request $i: "
  curl -s -i -H "X-User-Id: admin" "${BASE_URL}/demo/dynamic" | grep -E "(HTTP/|x-ratelimit-mode|x-ratelimit-action)"
done
echo "Result: Allowlisted clients bypass limiters and Redis completely."

echo -e "\n--- STEP 6: Reverting back to Shadow Mode ---"
curl -s -X POST "${BASE_URL}/admin/mode?mode=shadow" | jq .

echo -e "\n=========================================================="
echo " ROLLOUT DRILL COMPLETED SUCCESSFULLY ✅"
echo "=========================================================="
