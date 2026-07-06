#!/usr/bin/env bash
# collect_reviewer_data.sh
# -----------------------------------------------------------------------------
# Force-add a minimal, browsable, reproducibility-relevant subset of each
# data/<run>/ directory into git, for the manuscript ct-2026-00736q revision
# (Reviewer #1 Major 12 / Reviewer #2: open provenance for the benchmark systems).
#
# data/ is globally git-ignored (data/* plus *.dump *.data *.restart *.log), so
# every target here is staged with `git add -f`. The 44 GB of trajectories
# (*.dump) and checkpoints (*.restart/*.rst) are deliberately LEFT OUT — those
# go to the planned Zenodo DOI archive. Per-stage LAMMPS step logs (*.log) ARE
# staged where they were retained locally (see the run-log-coverage note in
# data/REVIEWER_DATA_README.md); missing logs are archive-only.
#
# Idempotent and re-runnable. Run from anywhere; it cd's to the repo root.
# -----------------------------------------------------------------------------
set -euo pipefail
shopt -s nullglob globstar

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- Run selection -----------------------------------------------------------
# Each machine has its own replicate set. Pick runs in priority order:
#   * explicit args :  collect_reviewer_data.sh PVC2 PVC3 PE4 PEG1 ...
#   * auto-discover :  collect_reviewer_data.sh auto    (every data/<dir> that
#                      has a run_log.md, excluding TEMPLATE / CALIB_* / archive / _*)
#   * no args       :  the DEFAULT_RUNS list below (this machine's committed 21).
DEFAULT_RUNS=(
  PE1 PE2 PE3
  PLA1 PLA2 PLA3 PLA4
  PMMA1 PMMA2 PMMA3
  PEEK1 PEEK2 PEEK3
  PSU1 PSU2 PSU4
  cis-PBD1 cis-PBD-2 cis-PBD3 cis-PBD4
  PVC1
)
if [ "${1:-}" = "auto" ]; then
  RUNS=()
  for p in data/*/run_log.md; do
    [ -e "$p" ] || continue
    r="$(basename "$(dirname "$p")")"
    case "$r" in TEMPLATE|CALIB_*|archive|_*) continue ;; esac
    RUNS+=( "$r" )
  done
  echo "auto-discovered ${#RUNS[@]} runs: ${RUNS[*]}"
elif [ "$#" -gt 0 ]; then
  RUNS=( "$@" )
else
  RUNS=( "${DEFAULT_RUNS[@]}" )
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
echo "Staged reviewer-data files: $(git diff --cached --name-only -- data/ | wc -l)"
echo "Done. Review with: git diff --cached --name-only -- data/ | less"
