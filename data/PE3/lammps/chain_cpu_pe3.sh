#!/bin/bash
# PE3 manual CPU chain — Kokkos -k on t 1 (no CUDA init), MPI=8
# Generated as workaround: run_lammps_chain engine=kokkos always uses -k on g 1

set -euo pipefail

CHAIN_ID="cpu_pe3"
LMP=/home/arz2/lammps-install/bin/lmp
OFFLOAD_FLAGS=""
MPI=8
BASE=/home/arz2/PolyJarvis/data/PE3/lammps

PROGRESS="${BASE}/chain_cpu_pe3_progress.jsonl"
SENTINEL=/tmp/polyjarvis/sentinels/done_cpu_pe3.json
PIDFILE=/tmp/polyjarvis/sentinels/pid_cpu_pe3

mkdir -p /tmp/polyjarvis/sentinels
echo $$ > "$PIDFILE"
> "$PROGRESS"

log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }

sentinel_ok()   { echo "{\"run_id\":\"cpu_pe3\",\"status\":\"completed\"}" > "$SENTINEL"; }
sentinel_fail() { echo "{\"run_id\":\"cpu_pe3\",\"status\":\"failed\",\"stage\":\"$1\"}" > "$SENTINEL"; }

unset OPAL_PREFIX
unset CUDA_VISIBLE_DEVICES
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}

LAUNCH="mpirun -np $MPI $LMP"

run_stage() {
    local stage=$1
    local dir="${BASE}/${stage}"
    echo "=== Starting stage: $stage ==="
    log_start "$stage"
    cd "$dir"
    if $LAUNCH -in "${stage}.in" >> "${BASE}/chain_cpu_pe3.log" 2>&1; then
        log_done "$stage"
        echo "=== Done: $stage ==="
    else
        log_fail "$stage"
        sentinel_fail "$stage"
        echo "FAILED: $stage" >&2
        exit 1
    fi
}

trap 'sentinel_fail "unknown"; exit 1' ERR

run_stage minimize
run_stage nvt_softheat
run_stage npt_compress
run_stage npt_pppm
run_stage npt_cool_melt
run_stage npt_melt
run_stage npt_cool
run_stage nvt_production
run_stage npt_production

sentinel_ok
echo "=== Chain cpu_pe3 complete ==="
