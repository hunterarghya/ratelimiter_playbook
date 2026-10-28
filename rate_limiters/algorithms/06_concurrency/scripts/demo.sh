#!/usr/bin/env bash
# Demo script for Concurrency rate limiter
# Usage:
#   make up P=concurrency
#   ./rate_limiters/algorithms/06_concurrency/scripts/demo.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8106}"
IDENTITY="user_$(date +%s)"

echo "=================================================="
echo " Concurrency Rate Limiter Live Demonstration"
echo " Target: ${BASE_URL}  |  Identity: ${IDENTITY}"
echo "=================================================="

echo ""
echo "--- 1. Firing 3 rapid requests (Limit: 2 concurrent slots) ---"
for i in 1 2 3; do
    echo -n "Request #$i: "
    curl -s -o /dev/null -w "HTTP %{http_code} | Remaining: %{header{ratelimit-remaining}} | Retry-After: %{header{retry-after}}\n" \
        -H "X-User-Id: ${IDENTITY}" \
        "${BASE_URL}/demo/limited"
    sleep 0.05
done

echo ""
echo "--- 2. Inspecting active leases in Redis via /debug/state ---"
curl -s "${BASE_URL}/debug/state?identity=${IDENTITY}"

echo ""
echo ""
echo "--- 3. Sleeping 1 second for leases to complete/release, then retrying ---"
sleep 1

echo -n "Request after slot freed: "
curl -s -o /dev/null -w "HTTP %{http_code} | Remaining: %{header{ratelimit-remaining}}\n" \
    -H "X-User-Id: ${IDENTITY}" \
    "${BASE_URL}/demo/limited"
echo ""
