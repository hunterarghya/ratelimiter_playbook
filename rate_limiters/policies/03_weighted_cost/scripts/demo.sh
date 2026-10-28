#!/usr/bin/env bash
# Demo script for Weighted Cost rate limiter
# Usage:
#   make up P=weighted-cost
#   ./rate_limiters/policies/03_weighted_cost/scripts/demo.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8203}"
IDENTITY="user_$(date +%s)"

echo "=================================================="
echo " Weighted Cost Rate Limiter Live Demonstration"
echo " Target: ${BASE_URL}  |  Identity: ${IDENTITY}"
echo " Burst Capacity: 5 cost units per period"
echo "=================================================="

echo ""
echo "--- 1. Cheap Query (cost = 1 unit) ---"
curl -s -w "\nHTTP %{http_code} | Remaining: %{header{ratelimit-remaining}} | Cost: %{header{x-ratelimit-cost}}\n" \
    -H "X-User-Id: ${IDENTITY}" \
    "${BASE_URL}/demo/query"

echo ""
echo "--- 2. Medium Report (cost = 2 units) ---"
curl -s -w "\nHTTP %{http_code} | Remaining: %{header{ratelimit-remaining}} | Cost: %{header{x-ratelimit-cost}}\n" \
    -H "X-User-Id: ${IDENTITY}" \
    "${BASE_URL}/demo/report"

echo ""
echo "--- 3. Heavy Batch Export (cost = 4 units, may be denied after report) ---"
curl -s -w "\nHTTP %{http_code} | Remaining: %{header{ratelimit-remaining}} | Cost: %{header{x-ratelimit-cost}}\n" \
    -H "X-User-Id: ${IDENTITY}" \
    "${BASE_URL}/demo/export"

echo ""
echo "--- 4. Impossible Request: cost = 100 > burst = 5 (Permanently Rejected) ---"
echo "Notice: Returns HTTP 422 (permanent error), NEVER a retryable 429!"
curl -s -w "\nHTTP %{http_code}\n" \
    -H "X-User-Id: ${IDENTITY}" \
    "${BASE_URL}/demo/oversized"

echo ""
echo "--- 5. Dynamic LLM Token Settle: Reserve 4 tokens upfront, settle actual ---"
LLM_ID="llm_user_$(date +%s)"
curl -s -X POST "${BASE_URL}/demo/llm" \
    -H "Content-Type: application/json" \
    -H "X-User-Id: ${LLM_ID}" \
    -d '{"prompt": "Hello world", "estimated_tokens": 4}' \
    | jq .

echo ""
echo "--- 6. Inspecting Redis state via /debug/state ---"
curl -s "${BASE_URL}/debug/state?identity=${LLM_ID}" | jq .
echo ""
