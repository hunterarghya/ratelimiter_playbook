#!/usr/bin/env bash
# Demo script for Shadow Mode rate limiter
# Usage:
#   make up P=shadow-mode
#   ./rate_limiters/policies/05_shadow_mode/scripts/demo.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8205}"

echo "=========================================================="
echo " Demo: Shadow Mode & Allowlist Rate Limiter"
echo " Base URL: ${BASE_URL}"
echo "=========================================================="

echo -e "\n1. Allowlist Bypass (user:admin):"
for i in {1..3}; do
  echo -n "Request $i: "
  curl -s -i -H "X-User-Id: admin" "${BASE_URL}/demo/allowlist" | grep -E "(HTTP/|x-ratelimit-mode|x-ratelimit-action)"
done

echo -e "\n2. Shadow Mode (user:alice rapid burst):"
echo "Notice all requests return 200 OK, but start reporting shadow_denied once burst is exceeded!"
for i in {1..8}; do
  echo -n "Request $i: "
  curl -s -i -H "X-User-Id: alice" "${BASE_URL}/demo/shadow" | grep -E "(HTTP/|x-ratelimit-action|x-ratelimit-would-block)" || true
done

echo -e "\n3. Enforce Mode (user:bob rapid burst):"
echo "Notice requests return 200 OK until burst is exhausted, then return 429 Too Many Requests!"
for i in {1..7}; do
  echo -n "Request $i: "
  curl -s -i -H "X-User-Id: bob" "${BASE_URL}/demo/enforce" | grep -E "(HTTP/|x-ratelimit-action|retry-after)" || true
done

echo -e "\n4. Inspect Prometheus Metrics:"
curl -s "${BASE_URL}/metrics" | grep -E "(rl_shadow_denied_total|rl_bypassed_total|rl_decisions_total)" | head -n 10

echo -e "\n=========================================================="
echo " For zero-code-change rollout drill, run:"
echo " ./rate_limiters/policies/05_shadow_mode/scripts/rollout_drill.sh"
echo "=========================================================="
