#!/usr/bin/env bash
# Demo script for Token Bucket rate limiter
# Usage:
#   make up P=token-bucket
#   ./rate_limiters/algorithms/04_token_bucket/scripts/demo.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8104}"
IDENTITY="user_$(date +%s)"

echo "=================================================="
echo " Token Bucket Rate Limiter Live Demonstration"
echo " Target: ${BASE_URL}  |  Identity: ${IDENTITY}"
echo "=================================================="

echo ""
echo "--- 1. Firing immediate burst of 6 requests (Limit: 5 burst) ---"
for i in $(seq 1 6); do
    echo -n "Request #$i: "
    curl -s -o /dev/null -w "HTTP %{http_code} | Remaining: %{header{ratelimit-remaining}} | Retry-After: %{header{retry-after}}\n" \
        -H "X-User-Id: ${IDENTITY}" \
        "${BASE_URL}/demo/limited"
    sleep 0.05
done

echo ""
echo "--- 2. Inspecting Redis state via /debug/state ---"
curl -s "${BASE_URL}/debug/state?identity=${IDENTITY}"

echo ""
echo ""
echo "--- 3. Sleeping 2 seconds to allow lazy token refill, then retrying ---"
sleep 2

echo -n "Request after 2s refill: "
curl -s -o /dev/null -w "HTTP %{http_code} | Remaining: %{header{ratelimit-remaining}}\n" \
    -H "X-User-Id: ${IDENTITY}" \
    "${BASE_URL}/demo/limited"
echo ""
