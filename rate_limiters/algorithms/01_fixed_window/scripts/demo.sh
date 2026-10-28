#!/usr/bin/env bash
set -euo pipefail

echo "=============================================="
echo "Scenario 1: Calm traffic (steady)"
echo "=============================================="
python -m tools.traffic --project fixed-window --scenario steady | python -m tools.viz

echo ""
echo "=============================================="
echo "Scenario 2: Burst then abuse (burst)"
echo "=============================================="
python -m tools.traffic --project fixed-window --scenario burst | python -m tools.viz

echo ""
echo "=============================================="
echo "Scenario 3: Fixed window boundary spike flaw"
echo "=============================================="
python -m tools.traffic --project fixed-window --scenario boundary | python -m tools.viz
