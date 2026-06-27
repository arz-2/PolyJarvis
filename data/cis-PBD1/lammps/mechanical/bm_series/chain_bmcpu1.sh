#!/bin/bash
# PolyJarvis CPU chain bmcpu1 — Murnaghan BM pressure series (5 NPT runs, P=1/100/300/600/1000 atm)
# CPU MPI=8 override (R-02). Mirrors engine sentinel/progress format.
set -uo pipefail

CHAIN_ID=bmcpu1
LMP=/home/arz2/lammps-install/bin/lmp
MPI=8
BMDIR=/home/arz2/PolyJarvis/data/cis-PBD1/lammps/mechanical/bm_series

PROGRESS="$BMDIR/chain_bmcpu1_progress.jsonl"
SENTDIR=/tmp/polyjarvis/sentinels
mkdir -p "$SENTDIR"
SENTINEL="$SENTDIR/done_bmcpu1.json"
PIDFILE="$SENTDIR/pid_bmcpu1"

log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
sentinel_ok()   { echo "{\"run_id\":\"$CHAIN_ID\",\"status\":\"completed\"}" > "$SENTINEL"; }
sentinel_fail() { echo "{\"run_id\":\"$CHAIN_ID\",\"status\":\"failed\",\"stage\":\"$1\"}" > "$SENTINEL"; }

export CUDA_VISIBLE_DEVICES=""
echo $$ > "$PIDFILE"

run_stage() {
  local P=$1
  local name="bm_P${P}"
  local wdir="$BMDIR/bm_P${P}"
  cd "$wdir"
  log_start "$name"
  if mpirun -np $MPI $LMP -in "$wdir/${name}.in" >> "$wdir/${name}_run.log" 2>&1; then
    log_done "$name"
  else
    log_fail "$name"; sentinel_fail "$name"
    echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"$name\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
    exit 1
  fi
}

for P in 1 100 300 600 1000; do
  run_stage $P
done

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":5,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
sentinel_ok
rm -f "$PIDFILE"
