#!/bin/bash
# PolyJarvis chain 27af49b8 — GPU1 restart (stages 4-5 only)
set -euo pipefail

CHAIN_ID=27af49b8
LMP=/home/arz2/lammps-install-kokkos/bin/lmp
OFFLOAD_FLAGS="-k on g 1 -sf kk -pk kokkos"
MPI=1
GPU_IDS=1
N_GPU=1

PROGRESS=/home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/chain_27af49b8_progress.jsonl

log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }

mkdir -p /tmp/polyjarvis/sentinels
SENTINEL=/tmp/polyjarvis/sentinels/done_27af49b8.json
PIDFILE=/tmp/polyjarvis/sentinels/pid_27af49b8
sentinel_ok()   { echo "{\"run_id\":\"27af49b8\",\"status\":\"completed\"}" > "$SENTINEL"; }
sentinel_fail() { echo "{\"run_id\":\"27af49b8\",\"status\":\"failed\",\"stage\":\"$1\"}" > "$SENTINEL"; }

export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
echo $$ > "$PIDFILE"
LAMMPS_LAUNCH="env CUDA_VISIBLE_DEVICES=$GPU_IDS $LMP $OFFLOAD_FLAGS"

# --- Stage 4/5: bm_P500 ---
mkdir -p /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/bm_P500
cd /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/bm_P500
log_start bm_P500
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/bm_P500/bm_P500.in >> /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/bm_P500/bm_P500.log 2>&1 \
  && log_done bm_P500 \
  || { log_fail bm_P500; sentinel_fail bm_P500; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"bm_P500\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 5/5: bm_P1000 ---
mkdir -p /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/bm_P1000
cd /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/bm_P1000
log_start bm_P1000
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/bm_P1000/bm_P1000.in >> /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/bm_P1000/bm_P1000.log 2>&1 \
  && log_done bm_P1000 \
  || { log_fail bm_P1000; sentinel_fail bm_P1000; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"bm_P1000\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":5,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
sentinel_ok
rm -f "$PIDFILE"
