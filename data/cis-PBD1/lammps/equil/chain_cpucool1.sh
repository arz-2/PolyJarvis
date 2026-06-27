#!/bin/bash
# PolyJarvis CPU chain cpucool1 — remaining equilibration (cool→nvt→npt_production)
# CPU MPI=8 override (R-02). Mirrors engine sentinel/progress format.
set -uo pipefail

CHAIN_ID=cpucool1
LMP=/home/arz2/lammps-install/bin/lmp
MPI=8
EQDIR=/home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil

PROGRESS="$EQDIR/chain_cpucool1_progress.jsonl"
SENTDIR=/tmp/polyjarvis/sentinels
mkdir -p "$SENTDIR"
SENTINEL="$SENTDIR/done_cpucool1.json"
PIDFILE="$SENTDIR/pid_cpucool1"

log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
sentinel_ok()   { echo "{\"run_id\":\"$CHAIN_ID\",\"status\":\"completed\"}" > "$SENTINEL"; }
sentinel_fail() { echo "{\"run_id\":\"$CHAIN_ID\",\"status\":\"failed\",\"stage\":\"$1\"}" > "$SENTINEL"; }

# Hide GPUs — force CPU-only execution
export CUDA_VISIBLE_DEVICES=""
# Record our own PID ($$ is the long-lived chain) for watch liveness
echo $$ > "$PIDFILE"

run_stage() {
  local name=$1 wdir=$2 script=$3
  mkdir -p "$wdir"; cd "$wdir"
  log_start "$name"
  if mpirun -np $MPI $LMP -in "$script" >> "$wdir/${name}.log" 2>&1; then
    log_done "$name"
  else
    log_fail "$name"; sentinel_fail "$name"
    echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"$name\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
    exit 1
  fi
}

run_stage npt_cool       "$EQDIR/npt_cool"       "$EQDIR/npt_cool/npt_cool.in"
run_stage nvt_production "$EQDIR/nvt_production" "$EQDIR/nvt_production/nvt_production.in"
run_stage npt_production "$EQDIR/npt_production" "$EQDIR/npt_production/npt_production.in"

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":3,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
sentinel_ok
rm -f "$PIDFILE"
