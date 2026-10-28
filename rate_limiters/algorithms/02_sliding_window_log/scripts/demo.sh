#!/usr/bin/env bash
set -euo pipefail

echo "=============================================="
echo "Scenario 1: Calm traffic (steady)"
echo "=============================================="
python -m tools.traffic --project sliding-log --scenario steady | python -m tools.viz

echo ""
echo "=============================================="
echo "Scenario 2: Burst then abuse (burst)"
echo "=============================================="
python -m tools.traffic --project sliding-log --scenario burst | python -m tools.viz

echo ""
echo "=============================================="
echo "Scenario 3: Race condition demo (Naive vs Lua)"
echo "=============================================="
PYTHONPATH=. python -m rate_limiters.algorithms.02_sliding_window_log.scripts.race_demo
