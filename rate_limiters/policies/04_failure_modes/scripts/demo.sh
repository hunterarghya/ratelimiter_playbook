#!/usr/bin/env bash
# Demo script for Failure Modes rate limiter under normal conditions
# Usage:
#   make up P=failure-modes
#   ./rate_limiters/policies/04_failure_modes/scripts/demo.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8204}"
IDENTITY="user:alice"

echo "=========================================================="
echo " Demo: Failure Modes Rate Limiter (Normal Operation)"
echo " Base URL: ${BASE_URL}"
echo "=========================================================="

echo -e "\n1. Check Health & Metrics:"
curl -s "${BASE_URL}/health" | jq .
curl -s "${BASE_URL}/metrics" | grep "rl_decisions_total" | head -n 5

echo -e "\n2. Testing /demo/fail-open (Allowed under Redis):"
for i in {1..3}; do
  echo -n "Request $i: "
  curl -s -i -H "X-User-Id: ${IDENTITY}" "${BASE_URL}/demo/fail-open" | head -n 1
done

echo -e "\n3. Testing /demo/fail-closed (Allowed under Redis):"
for i in {1..3}; do
  echo -n "Request $i: "
  curl -s -i -H "X-User-Id: ${IDENTITY}" "${BASE_URL}/demo/fail-closed" | head -n 1
done

echo -e "\n4. Testing /demo/fallback (Allowed under Redis):"
for i in {1..3}; do
  echo -n "Request $i: "
  curl -s -i -H "X-User-Id: ${IDENTITY}" "${BASE_URL}/demo/fallback" | head -n 1
done

echo -e "\n=========================================================="
echo " For simulated Redis outages, run:"
echo " ./rate_limiters/policies/04_failure_modes/scripts/chaos.sh"
echo "=========================================================="
