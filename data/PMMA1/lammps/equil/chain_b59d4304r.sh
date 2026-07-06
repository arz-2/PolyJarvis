#!/bin/bash
# PolyJarvis chain b59d4304r — RESUME of b59d4304 at MPI=8 + PPPM 1e-4
# Resumes stages 3-9 from nvt_softheat_out.data (stages 1-2 preserved). Do not edit.
set -uo pipefail

CHAIN_ID=b59d4304r
LMP=/home/arz2/lammps-install/bin/lmp
MPI=8
N_GPU=1
BASE=/home/arz2/PolyJarvis/data/PMMA1/lammps
PROGRESS=$BASE/chain_b59d4304r_progress.jsonl
SENTDIR=/tmp/polyjarvis/sentinels
SENTINEL=$SENTDIR/done_b59d4304r.json
mkdir -p "$SENTDIR"

export CUDA_VISIBLE_DEVICES=1
export OMP_NUM_THREADS=1

log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}"    >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}"  >> "$PROGRESS"; }
write_sentinel() { echo "{\"run_id\": \"b59d4304r\", \"status\": \"$1\", \"timestamp\": \"$(date -Iseconds)\", \"failed_at\": \"$2\"}" > "$SENTINEL"; }

run_stage() {
  local s=$1
  mkdir -p "$BASE/$s"
  cd "$BASE/$s"
  log_start "$s"
  if mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in "$BASE/$s/$s.in" > "$BASE/$s/$s.log" 2>&1; then
    log_done "$s"
  else
    log_fail "$s"
    write_sentinel failed "$s"
    exit 1
  fi
}

for s in npt_compress npt_pppm npt_cool nvt_production npt_production npt_cool300 npt_prod300; do
  run_stage "$s"
done

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":7,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
write_sentinel completed ""
