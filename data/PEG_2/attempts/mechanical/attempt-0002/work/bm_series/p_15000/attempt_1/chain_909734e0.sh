#!/bin/bash
# PolyJarvis chain 909734e0 — auto-generated, do not edit (engine=kokkos)
set -euo pipefail

CHAIN_ID=909734e0
LMP=/home/alexzhao/lammps-install-kokkos/bin/lmp
OFFLOAD_FLAGS="-k on g 1 -sf kk -pk kokkos"
MPI=1
GPU_IDS=3
N_GPU=1

# Progress log — one JSON object per line
PROGRESS=/home/alexzhao/PolyJarvis/data/PEG_2/attempts/mechanical/attempt-0002/work/bm_series/p_15000/attempt_1/chain_909734e0_progress.jsonl

log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }

# Completion sentinel — written by THIS nohup'd script so it survives an
# MCP-server restart (the in-process chain monitor is only a fast-path).
mkdir -p /tmp/polyjarvis/sentinels
SENTINEL=/tmp/polyjarvis/sentinels/done_909734e0.json
PIDFILE=/tmp/polyjarvis/sentinels/pid_909734e0
sentinel_ok()   { echo "{\"run_id\":\"909734e0\",\"status\":\"completed\"}" > "$SENTINEL"; }
sentinel_fail() { echo "{\"run_id\":\"909734e0\",\"status\":\"failed\",\"stage\":\"$1\"}" > "$SENTINEL"; }

export CUDA_VISIBLE_DEVICES=3
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
# Record our own PID so watch_run can check liveness ($$ is the long-lived chain).
echo $$ > "$PIDFILE"
LAMMPS_LAUNCH="env CUDA_VISIBLE_DEVICES=$GPU_IDS $LMP $OFFLOAD_FLAGS"

# --- Stage 1/1: bm_P15000 ---
mkdir -p /home/alexzhao/PolyJarvis/data/PEG_2/attempts/mechanical/attempt-0002/work/bm_series/p_15000/attempt_1/bm_P15000
cd /home/alexzhao/PolyJarvis/data/PEG_2/attempts/mechanical/attempt-0002/work/bm_series/p_15000/attempt_1/bm_P15000
log_start bm_P15000
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PEG_2/attempts/mechanical/attempt-0002/work/bm_series/p_15000/attempt_1/bm_P15000/bm_P15000.in >> /home/alexzhao/PolyJarvis/data/PEG_2/attempts/mechanical/attempt-0002/work/bm_series/p_15000/attempt_1/bm_P15000/bm_P15000_stdout.log 2>&1 \
  && log_done bm_P15000 \
  || { log_fail bm_P15000; sentinel_fail bm_P15000; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"bm_P15000\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":1,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
sentinel_ok
rm -f "$PIDFILE"

