#!/usr/bin/env bash
# Demo script for Identity Strategies rate limiter
# Usage:
#   make up P=identity
#   ./rate_limiters/policies/02_identity_strategies/scripts/demo.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8202}"
TIMESTAMP="$(date +%s)"
USER_ID="user_${TIMESTAMP}"
API_KEY="sk_live_demo_${TIMESTAMP}"
TENANT_ID="tenant_corp_${TIMESTAMP}"

echo "=================================================="
echo " Identity Strategies Rate Limiter Live Demo"
echo " Target: ${BASE_URL}"
echo "=================================================="

echo ""
echo "--- 1. Testing IP Identity Strategy (/demo/ip) ---"
for i in $(seq 1 3); do
    echo -n "Request #$i: "
    curl -s -o /dev/null -w "HTTP %{http_code} | Identity: %{header{x-ratelimit-identity}} | Remaining: %{header{ratelimit-remaining}}\n" \
        -H "X-Forwarded-For: 203.0.113.195" \
        "${BASE_URL}/demo/ip"
done

echo ""
echo "--- 2. Testing User Identity Strategy (/demo/user) ---"
for i in $(seq 1 3); do
    echo -n "Request #$i: "
    curl -s -o /dev/null -w "HTTP %{http_code} | Identity: %{header{x-ratelimit-identity}} | Remaining: %{header{ratelimit-remaining}}\n" \
        -H "X-User-Id: ${USER_ID}" \
        "${BASE_URL}/demo/user"
done

echo ""
echo "--- 3. Testing API Key Strategy (/demo/api-key) ---"
echo -n "API Key Request: "
curl -s -o /dev/null -w "HTTP %{http_code} | Identity: %{header{x-ratelimit-identity}} | Remaining: %{header{ratelimit-remaining}}\n" \
    -H "X-API-Key: ${API_KEY}" \
    "${BASE_URL}/demo/api-key"

echo ""
echo "--- 4. Testing Tenant Strategy (/demo/tenant) ---"
echo -n "Tenant Request: "
curl -s -o /dev/null -w "HTTP %{http_code} | Identity: %{header{x-ratelimit-identity}} | Remaining: %{header{ratelimit-remaining}}\n" \
    -H "X-Tenant-Id: ${TENANT_ID}" \
    "${BASE_URL}/demo/tenant"

echo ""
echo "--- 5. Testing Endpoint Strategy (/demo/endpoint) ---"
echo -n "Endpoint Request: "
curl -s -o /dev/null -w "HTTP %{http_code} | Identity: %{header{x-ratelimit-identity}} | Remaining: %{header{ratelimit-remaining}}\n" \
    "${BASE_URL}/demo/endpoint"

echo ""
echo "--- 6. Testing Global Strategy (/demo/global) ---"
echo -n "Global Request: "
curl -s -o /dev/null -w "HTTP %{http_code} | Identity: %{header{x-ratelimit-identity}} | Remaining: %{header{ratelimit-remaining}}\n" \
    "${BASE_URL}/demo/global"

echo ""
echo "--- 7. Testing Composite IP+User Strategy (/demo/ip-user) ---"
echo -n "Composite Request: "
curl -s -o /dev/null -w "HTTP %{http_code} | Identity: %{header{x-ratelimit-identity}} | Remaining: %{header{ratelimit-remaining}}\n" \
    -H "X-Forwarded-For: 198.51.100.10" \
    -H "X-User-Id: ${USER_ID}" \
    "${BASE_URL}/demo/ip-user"

echo ""
echo "--- 8. Testing Anonymous -> Authenticated Transition (/demo/transition) ---"
echo "Making 3 anonymous requests (limit: 3)..."
for i in $(seq 1 3); do
    echo -n "Anon #$i: "
    curl -s -o /dev/null -w "HTTP %{http_code} | Remaining: %{header{ratelimit-remaining}}\n" \
        -H "X-Forwarded-For: 192.0.2.1" \
        "${BASE_URL}/demo/transition"
done

echo -n "Anon #4 (should be 429): "
curl -s -o /dev/null -w "HTTP %{http_code} | Retry-After: %{header{retry-after}}\n" \
    -H "X-Forwarded-For: 192.0.2.1" \
    "${BASE_URL}/demo/transition"

echo -n "User Alice authenticates from same IP (has fresh user quota!): "
curl -s -o /dev/null -w "HTTP %{http_code} | Identity: %{header{x-ratelimit-identity}} | Remaining: %{header{ratelimit-remaining}}\n" \
    -H "X-Forwarded-For: 192.0.2.1" \
    -H "X-User-Id: alice_${TIMESTAMP}" \
    "${BASE_URL}/demo/transition"

echo ""
echo "--- 9. Inspecting Redis state via /debug/state ---"
curl -s "${BASE_URL}/debug/state"
echo ""
