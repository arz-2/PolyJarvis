#!/usr/bin/env bash
# Build the test-1 arm cells. BUILDS ONLY -- launches nothing, claims no GPU.
#
# Cell construction is CPU-only; only equilibration needs a GPU. The arms are staged
# unlaunched so a1's result selects which one gets GPU time:
#
#   a1 says COOLING PROTOCOL  -> arm E is the experiment that answers the reviewer
#   a1 says FORCE FIELD       -> arm B bounds the field's contribution
#
# a1 has now run: PMMA is decisively cooling-stage, PS is mixed (1 of 4 runs
# melt-deficient). Arm E is therefore the indicated arm for PMMA; arm B remains
# worthwhile on PS1's chemistry, which is the one cell with a real melt deficit.
#
# ARM E IS NOT `eq_annealing_cycles`. That parameter reaches no executor -- the
# workflow performs one heat/compress/cool pass regardless of its value, and
# validate_run_plan.py now fails a plan that sets it. Arm E is applied at
# equilibration time via generate_equilibration_workflow(add_melt_npt=True,
# melt_npt_steps=10*int(1.0e6/dt_fs)), not at build time, so no build below encodes it.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
EMC="$REPO/mcp-servers/mcp-emc-server/smiles_to_emc.py"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Sizing matches the archived anchors so arm A is a like-for-like baseline.
PMMA_SMILES='*CC(C)(C(=O)OC)*'   ; PMMA_DP=50 ; PMMA_NCHAIN=10
PS_SMILES='*CC(c1ccccc1)*'       ; PS_DP=40   ; PS_NCHAIN=10

build () {
  local name="$1" smiles="$2" field="$3" dp="$4" nchain="$5"
  local out="$HERE/$name"
  if [ -f "$out/${name}.data" ] || [ -f "$out/emc_build.data" ]; then
    echo "SKIP  $name (already built)"; return 0
  fi
  echo "BUILD $name  field=$field dp=$dp nchain=$nchain"
  mkdir -p "$out"
  python3 "$EMC" "$smiles" "$out" \
      --field "$field" --dp "$dp" --nchains "$nchain" \
      --density 0.6 --name "$name" > "$out/build.log" 2>&1 \
    || { echo "FAIL  $name -- see $out/build.log"; return 1; }
  echo "OK    $name"
}

# Arm A: PCFF anchor, rebuilt so both arms come from the same builder version.
build PMMA_armA_pcff "$PMMA_SMILES" pcff              "$PMMA_DP" "$PMMA_NCHAIN"
build PS_armA_pcff   "$PS_SMILES"   pcff              "$PS_DP"   "$PS_NCHAIN"

# Arm B: OPLS-AA 2024 -- all-atom, non-Class-II, cutoff-matched to PCFF (both 9.5/9.5),
# and fully KOKKOS-accelerated (multi/harmonic/kk exists; the field defines no impropers
# for esters or aromatics, so there is no host-side improper term).
build PMMA_armB_opls "$PMMA_SMILES" opls/2024/opls-aa "$PMMA_DP" "$PMMA_NCHAIN"
build PS_armB_opls   "$PS_SMILES"   opls/2024/opls-aa "$PS_DP"   "$PS_NCHAIN"

# Arm E uses the arm A cells; the heavy melt anneal is an equilibration-stage setting.
echo
echo "Arm E reuses the arm A cells (heavy melt anneal is set at equilibration:"
echo "  add_melt_npt=True, melt_npt_steps=10x int(1.0e6/dt_fs), 50x on rung 2)."
echo "Nothing has been launched. No GPU claimed."
