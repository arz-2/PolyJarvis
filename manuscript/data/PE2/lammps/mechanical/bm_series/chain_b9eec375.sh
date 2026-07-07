#!/bin/bash
# PolyJarvis chain b9eec375 — auto-generated, do not edit (engine=gpu)
set -euo pipefail

CHAIN_ID=b9eec375
LMP=/home/arz2/lammps-install/bin/lmp
OFFLOAD_FLAGS="-sf gpu -pk gpu 1"
MPI=1
GPU_IDS=3
N_GPU=1

# Progress log — one JSON object per line
PROGRESS=/home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/chain_b9eec375_progress.jsonl

log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }

# Completion sentinel — written by THIS nohup'd script so it survives an
# MCP-server restart (the in-process chain monitor is only a fast-path).
mkdir -p /tmp/polyjarvis/sentinels
SENTINEL=/tmp/polyjarvis/sentinels/done_b9eec375.json
PIDFILE=/tmp/polyjarvis/sentinels/pid_b9eec375
sentinel_ok()   { echo "{\"run_id\":\"b9eec375\",\"status\":\"completed\"}" > "$SENTINEL"; }
sentinel_fail() { echo "{\"run_id\":\"b9eec375\",\"status\":\"failed\",\"stage\":\"$1\"}" > "$SENTINEL"; }

export CUDA_VISIBLE_DEVICES=3
# Record our own PID so watch_run can check liveness ($$ is the long-lived chain).
echo $$ > "$PIDFILE"
LAMMPS_LAUNCH="env CUDA_VISIBLE_DEVICES=$GPU_IDS $LMP $OFFLOAD_FLAGS"

# --- Stage 1/5: bm_P1 ---
mkdir -p /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P1
cd /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P1
log_start bm_P1
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P1/bm_P1.in >> /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P1/bm_P1_stdout.log 2>&1 \
  && log_done bm_P1 \
  || { log_fail bm_P1; sentinel_fail bm_P1; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"bm_P1\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 2/5: bm_P100 ---
mkdir -p /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P100
cd /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P100
log_start bm_P100
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P100/bm_P100.in >> /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P100/bm_P100_stdout.log 2>&1 \
  && log_done bm_P100 \
  || { log_fail bm_P100; sentinel_fail bm_P100; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"bm_P100\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 3/5: bm_P300 ---
mkdir -p /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P300
cd /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P300
log_start bm_P300
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P300/bm_P300.in >> /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P300/bm_P300_stdout.log 2>&1 \
  && log_done bm_P300 \
  || { log_fail bm_P300; sentinel_fail bm_P300; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"bm_P300\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 4/5: bm_P600 ---
mkdir -p /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P600
cd /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P600
log_start bm_P600
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P600/bm_P600.in >> /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P600/bm_P600_stdout.log 2>&1 \
  && log_done bm_P600 \
  || { log_fail bm_P600; sentinel_fail bm_P600; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"bm_P600\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 5/5: bm_P1000 ---
mkdir -p /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P1000
cd /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P1000
log_start bm_P1000
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P1000/bm_P1000.in >> /home/arz2/PolyJarvis/data/PE2/lammps/mechanical/bm_series/bm_P1000/bm_P1000_stdout.log 2>&1 \
  && log_done bm_P1000 \
  || { log_fail bm_P1000; sentinel_fail bm_P1000; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"bm_P1000\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":5,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
sentinel_ok
rm -f "$PIDFILE"

