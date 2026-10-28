#!/usr/bin/env bash
# Demo script for Multi-Rule rate limiter
# Usage:
#   make up P=multi-rule
#   ./rate_limiters/policies/01_multi_rule/scripts/demo.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8201}"
IDENTITY="user_$(date +%s)"

echo "=================================================="
echo " Multi-Rule Rate Limiter Live Demonstration"
echo " Target: ${BASE_URL}  |  Identity: ${IDENTITY}"
echo "=================================================="

echo ""
echo "--- 1. Firing 6 rapid requests (Per-sec limit: 5, Hourly limit: 10) ---"
for i in $(seq 1 6); do
    echo -n "Request #$i: "
    curl -s -o /dev/null -w "HTTP %{http_code} | Remaining: %{header{ratelimit-remaining}} | Retry-After: %{header{retry-after}}\n" \
        -H "X-User-Id: ${IDENTITY}" \
        "${BASE_URL}/demo/limited"
    sleep 0.05
done

echo ""
echo "--- 2. Inspecting all rule keys in Redis via /debug/state ---"
curl -s "${BASE_URL}/debug/state?identity=${IDENTITY}"

echo ""
echo ""
echo "--- 3. Sleeping 1 second to clear per-second window, then retrying ---"
sleep 1

echo -n "Request after 1s: "
curl -s -o /dev/null -w "HTTP %{http_code} | Remaining: %{header{ratelimit-remaining}}\n" \
    -H "X-User-Id: ${IDENTITY}" \
    "${BASE_URL}/demo/limited"
echo ""
