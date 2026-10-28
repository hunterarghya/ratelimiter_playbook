#!/usr/bin/env bash
# Demo script for Sliding Window Counter rate limiter
# Usage: ./demo.sh [limit] [period_seconds]
#   make up P=sliding-counter
#   ./rate_limiters/algorithms/03_sliding_window_counter/scripts/demo.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8103}"
LIMIT="${1:-5}"
PERIOD="${2:-10}"

echo "================================================="
echo " Sliding Window Counter · limit ${LIMIT}/${PERIOD}s"
echo " ${BASE_URL}/demo/limited"
echo "================================================="
echo ""

echo "--- Health check ---"
curl -s "${BASE_URL}/health" | python -m json.tool
echo ""

echo "--- Sending ${LIMIT} requests (should all be allowed) ---"
for i in $(seq 1 "${LIMIT}"); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "X-User-Id: demo-alice" "${BASE_URL}/demo/limited")
    echo "  Request #${i}: HTTP ${STATUS}"
done

echo ""
echo "--- Sending 2 more (should be denied 429) ---"
for i in $(seq 1 2); do
    RESP=$(curl -s -w "\n%{http_code}" -H "X-User-Id: demo-alice" "${BASE_URL}/demo/limited")
    STATUS=$(echo "$RESP" | tail -1)
    BODY=$(echo "$RESP" | head -n -1)
    echo "  Request #$((LIMIT + i)): HTTP ${STATUS}"
    if [ "${STATUS}" = "429" ]; then
        echo "    ${BODY}" | python -m json.tool 2>/dev/null || echo "    ${BODY}"
    fi
done

echo ""
echo "--- Debug: current Redis state ---"
curl -s "${BASE_URL}/debug/state?identity=user:demo-alice" | python -m json.tool
echo ""
echo "Done."
