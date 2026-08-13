#!/usr/bin/env bash
# Test 1 free leg. No simulation, no GPU: reads archived .data/.in files and
# db/polymer_db.sqlite, writes only into results/.
#
# a1 is the gating step -- it decides whether the funded arms target the force field
# (arm B) or the cooling protocol (arm E), so it runs before anything is launched.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for step in a0_extend_decomposition \
            a1_experimental_melt_reference \
            a2_protocol_audit \
            a3_plan_vs_deck_audit; do
  echo "── $step ──"
  python3 "$HERE/$step.py"
  echo
done

echo "Outputs in $HERE/results/"
