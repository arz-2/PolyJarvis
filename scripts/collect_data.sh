#!/usr/bin/env bash
# collect_data.sh
# -----------------------------------------------------------------------------
# Provenance collection + analysis regeneration for the benchmark data release.
#
# 1) COLLECT — force-add a minimal, browsable, reproducibility-relevant subset
#    of each data/<run>/ directory into git. data/ is globally git-ignored
#    (data/* plus *.dump *.data *.restart *.log), so every target here is
#    staged with `git add -f`. Trajectories (*.dump, ~44 GB) and checkpoints
#    (*.restart/*.rst) are deliberately LEFT OUT — those live in the archived
#    DOI release. Per-stage LAMMPS step logs (*.log) ARE staged where they were
#    retained (see the log-coverage note in data/README.md).
#
# 2) REGEN — re-derive the paper's analysis artifacts from the collected data:
#    the paper/csv/ tables + per-replicate Tg bins, and the derived figures
#    (paper/figures/). Three csv families are SOURCE data computed from the
#    archived trajectories and are inputs here, not outputs:
#    <family>_rdf.csv, density_homogeneity_300k.csv,
#    structure_diagnostics_300k_local.csv.
#
# Usage:
#   collect_data.sh                 auto-discover every data/<run> with a
#                                   run_log.md (excludes TEMPLATE / CALIB_* /
#                                   archive / _* / RECOV_* / *_AGENT)
#   collect_data.sh PE1 PVC2 ...    explicit run list (no exclusions)
#   collect_data.sh --no-regen      collect only; skip csv/figure regeneration
#
# Idempotent and re-runnable. Run from anywhere; it cd's to the repo root.
# -----------------------------------------------------------------------------
set -euo pipefail
shopt -s nullglob globstar

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- Argument parsing ----------------------------------------------------------
REGEN=1
RUNS=()
for a in "$@"; do
  case "$a" in
    --no-regen) REGEN=0 ;;
    auto)       ;;        # legacy keyword — auto-discovery is now the default
    *)          RUNS+=( "$a" ) ;;
  esac
done

# --- Run selection -------------------------------------------------------------
# No explicit runs => auto-discover every data/<dir> that has a run_log.md,
# excluding non-benchmark dirs (templates, calibration cells, archive, registries,
# and the fault-injection / one-off agent runs — pass those explicitly if needed).
if [ "${#RUNS[@]}" -eq 0 ]; then
  for p in data/*/run_log.md; do
    [ -e "$p" ] || continue
    r="$(basename "$(dirname "$p")")"
    case "$r" in TEMPLATE|CALIB_*|archive|_*|RECOV_*|*_AGENT) continue ;; esac
    RUNS+=( "$r" )
  done
  echo "auto-discovered ${#RUNS[@]} runs: ${RUNS[*]}"
fi

# Final equilibrated structures to include (basename allowlist). Covers both
# glassy (npt_prod300_out.data) and rubbery (npt_production_out.data) regimes.
# Intermediate stage *_out.data are excluded. The initial packed cell is added
# separately (canonical cell/cell.data only) to avoid the equil/ duplicate copy.
STRUCT_NAMES=( npt_production_out.data npt_prod300_out.data )

add_if_any() {
  # git add -f only the args that actually exist (nullglob already drops misses).
  [ "$#" -gt 0 ] && git add -f -- "$@" || true
}

for r in "${RUNS[@]}"; do
  d="data/$r"
  if [ ! -d "$d" ]; then
    echo "WARN: $d not found, skipping" >&2
    continue
  fi
  echo "==> $r"

  # Decision / recovery logs + run metadata
  add_if_any "$d"/run_log.md "$d"/Task.txt

  # Analysis outputs, raw Tg-fit data, seeds, BM stats, structural diagnostics
  add_if_any "$d"/raw/*.json "$d"/raw/*.csv "$d"/raw/*.md "$d"/raw/*.txt
  # per-rate Tg subdirs (raw/tg_r40/, raw/deform_slow/, ...)
  add_if_any "$d"/raw/**/*.json "$d"/raw/**/*.csv "$d"/raw/**/*.md "$d"/raw/**/*.txt

  # Figures (top-level + per-rate subdirs e.g. graphs/tg_r40/)
  add_if_any "$d"/graphs/*.png "$d"/graphs/**/*.png

  # Initial packed cell — canonical copy only (cell/cell.data), else top-level
  # lammps/cell.data. Skip the equil/ working duplicate.
  if   [ -f "$d/lammps/cell/cell.data" ]; then add_if_any "$d/lammps/cell/cell.data"
  elif [ -f "$d/lammps/cell.data" ];      then add_if_any "$d/lammps/cell.data"
  fi

  # Input scripts, FF params, chain submit scripts, workflow/tool-call traces,
  # and final structures — all under lammps/.
  if [ -d "$d/lammps" ]; then
    find_args=( -name '*.in' -o -name 'emc_build.params' -o -name '*.sh' -o -name '*.jsonl' -o -name '*.log' )
    for n in "${STRUCT_NAMES[@]}"; do find_args+=( -o -name "$n" ); done
    find "$d/lammps" -type f \( "${find_args[@]}" \) -print0 \
      | xargs -0 -r git add -f --
  fi
done

echo
echo "Staged data files: $(git diff --cached --name-only -- data/ | wc -l)"

# --- Regenerate derived analysis artifacts (paper/csv + figures) ---------------
if [ "$REGEN" -eq 1 ]; then
  echo
  echo "==> Regenerating paper/csv tables + figures from data/"
  python3 paper/gen_figure4_tg_curves.py               # <RUN>_bins.csv + tg_selection_manifest.json + Tg-curves figure
  python3 paper/gen_table_bulk_modulus_robustness.py   # bulk_modulus_robustness{,_family}.csv
  python3 paper/gen_table_compute_cost.py              # compute_cost{,_class}.csv
  python3 paper/gen_table_structure_diagnostics.py     # structure_diagnostics{,_perrun}.csv + manifest
  python3 paper/gen_figure3_density_parity.py          # density parity figure
  python3 paper/gen_figure5_bulk_modulus.py            # bulk-modulus figure
  python3 paper/gen_figure6_rdf.py                     # RDF figure (from the committed csv/<family>_rdf.csv)
  git add paper/csv
  echo "Regenerated csv staged; figures written to paper/figures/ (untracked)."
fi

echo "Done. Review with: git diff --cached --name-only | less"
