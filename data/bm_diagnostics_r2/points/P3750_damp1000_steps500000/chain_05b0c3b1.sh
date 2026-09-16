#!/bin/bash
# PolyJarvis chain 05b0c3b1 — auto-generated, do not edit (engine=kokkos)
set -euo pipefail

CHAIN_ID=05b0c3b1
LMP=/home/arz2/lammps-install-kokkos/bin/lmp
OFFLOAD_FLAGS="-k on g 1 -sf kk -pk kokkos"
MPI=1
GPU_IDS=3
N_GPU=1

# Progress log — one JSON object per line
PROGRESS=/home/arz2/PolyJarvis_v2/data/bm_diagnostics_r2/points/P3750_damp1000_steps500000/chain_05b0c3b1_progress.jsonl

log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }

# Completion sentinel — written by THIS nohup'd script so it survives an
# MCP-server restart (the in-process chain monitor is only a fast-path).
mkdir -p /tmp/polyjarvis/sentinels
SENTINEL=/tmp/polyjarvis/sentinels/done_05b0c3b1.json
PIDFILE=/tmp/polyjarvis/sentinels/pid_05b0c3b1
sentinel_ok()   { echo "{\"run_id\":\"05b0c3b1\",\"status\":\"completed\"}" > "$SENTINEL"; }
sentinel_fail() { echo "{\"run_id\":\"05b0c3b1\",\"status\":\"failed\",\"stage\":\"$1\"}" > "$SENTINEL"; }

export CUDA_VISIBLE_DEVICES=3
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
# Record our own PID so watch_run can check liveness ($$ is the long-lived chain).
echo $$ > "$PIDFILE"
LAMMPS_LAUNCH="env CUDA_VISIBLE_DEVICES=$GPU_IDS $LMP $OFFLOAD_FLAGS"

# --- Stage 1/1: bm_P3750 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/bm_diagnostics_r2/points/P3750_damp1000_steps500000/bm_P3750
cd /home/arz2/PolyJarvis_v2/data/bm_diagnostics_r2/points/P3750_damp1000_steps500000/bm_P3750
log_start bm_P3750
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/bm_diagnostics_r2/points/P3750_damp1000_steps500000/bm_P3750/bm_P3750.in >> /home/arz2/PolyJarvis_v2/data/bm_diagnostics_r2/points/P3750_damp1000_steps500000/bm_P3750/bm_P3750_stdout.log 2>&1 \
  && log_done bm_P3750 \
  || { log_fail bm_P3750; sentinel_fail bm_P3750; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"bm_P3750\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":1,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
sentinel_ok
rm -f "$PIDFILE"

