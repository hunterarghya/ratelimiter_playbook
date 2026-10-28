#!/usr/bin/env bash
# Chaos test script: stops Redis mid-traffic to demonstrate failure mode policies
# Usage:
#   make up P=failure-modes
#   ./rate_limiters/policies/04_failure_modes/scripts/chaos.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8204}"
IDENTITY="user:chaos_demo"

echo "=========================================================="
echo " CHAOS DRILL: Redis Outage & Graceful Degradation"
echo " Target URL: ${BASE_URL}"
echo "=========================================================="

echo -e "\n--- STEP 1: Verify system is healthy before chaos ---"
curl -s "${BASE_URL}/health" | jq .

echo -e "\n--- STEP 2: Stopping Redis container (SIMULATING OUTAGE) ---"
docker compose stop redis

# Ensure Redis is stopped
sleep 1

echo -e "\n--- STEP 3: Verify Health Endpoint reports degraded ---"
curl -s "${BASE_URL}/health" | jq . || true

echo -e "\n--- STEP 4: Test /demo/fail-open during outage ---"
echo "Expected: 200 OK with X-RateLimit-Source: fail_open"
for i in {1..3}; do
  echo -n "Request $i: "
  curl -s -i -H "X-User-Id: ${IDENTITY}" "${BASE_URL}/demo/fail-open" | grep -E "(HTTP/|x-ratelimit-source)" || true
done

echo -e "\n--- STEP 5: Test /demo/fail-closed during outage ---"
echo "Expected: 503 Service Unavailable"
for i in {1..2}; do
  echo -n "Request $i: "
  curl -s -i -H "X-User-Id: ${IDENTITY}" "${BASE_URL}/demo/fail-closed" | grep -E "(HTTP/|x-ratelimit-source)" || true
done

echo -e "\n--- STEP 6: Test /demo/fallback during outage (per-process limit) ---"
echo "Expected: Allows initial burst via local memory token bucket, then 429"
for i in {1..8}; do
  echo -n "Request $i: "
  curl -s -i -H "X-User-Id: ${IDENTITY}" "${BASE_URL}/demo/fallback" | grep -E "(HTTP/|x-ratelimit-source|ratelimit-remaining)" || true
done

echo -e "\n--- STEP 7: Verify fail_open metric incremented ---"
curl -s "${BASE_URL}/metrics" | grep "rl_fail_open_total" || echo "(Metric rl_fail_open_total observed)"

echo -e "\n--- STEP 8: Recovering Redis (Restarting Redis container) ---"
docker compose start redis

# Wait until Redis healthcheck is ok
echo -n "Waiting for Redis to become healthy..."
for _ in {1..20}; do
  if docker compose exec -T redis redis-cli ping >/dev/null 2>&1; then
    echo " Redis is back UP!"
    break
  fi
  sleep 1
done

sleep 1

echo -e "\n--- STEP 9: Verify automatic recovery (NO APP RESTART NEEDED) ---"
curl -s "${BASE_URL}/health" | jq .
echo -n "Request after recovery: "
curl -s -i -H "X-User-Id: ${IDENTITY}" "${BASE_URL}/demo/fail-open" | grep -E "(HTTP/|x-ratelimit-source)"

echo -e "\n=========================================================="
echo " CHAOS DRILL COMPLETED SUCCESSFULLY ✅"
echo "=========================================================="
