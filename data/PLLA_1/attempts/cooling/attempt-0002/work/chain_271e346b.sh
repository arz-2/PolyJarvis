#!/bin/bash
# PolyJarvis chain 271e346b — auto-generated, do not edit (engine=kokkos)
set -euo pipefail

CHAIN_ID=271e346b
LMP=/home/arz2/lammps-install-kokkos/bin/lmp
OFFLOAD_FLAGS="-k on g 1 -sf kk -pk kokkos"
MPI=1
GPU_IDS=1
N_GPU=1

# Progress log — one JSON object per line
PROGRESS=/home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/chain_271e346b_progress.jsonl

log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }

# Completion sentinel — written by THIS nohup'd script so it survives an
# MCP-server restart (the in-process chain monitor is only a fast-path).
mkdir -p /tmp/polyjarvis/sentinels
SENTINEL=/tmp/polyjarvis/sentinels/done_271e346b.json
PIDFILE=/tmp/polyjarvis/sentinels/pid_271e346b
sentinel_ok()   { echo "{\"run_id\":\"271e346b\",\"status\":\"completed\"}" > "$SENTINEL"; }
sentinel_fail() { echo "{\"run_id\":\"271e346b\",\"status\":\"failed\",\"stage\":\"$1\"}" > "$SENTINEL"; }

export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
# Record our own PID so watch_run can check liveness ($$ is the long-lived chain).
echo $$ > "$PIDFILE"
LAMMPS_LAUNCH="env CUDA_VISIBLE_DEVICES=$GPU_IDS $LMP $OFFLOAD_FLAGS"

# --- Stage 1/14: cool_block_01 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_01
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_01
log_start cool_block_01
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_01/cool_block_01.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_01/cool_block_01_run.log 2>&1 \
  && log_done cool_block_01 \
  || { log_fail cool_block_01; sentinel_fail cool_block_01; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_01\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 2/14: cool_block_02 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_02
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_02
log_start cool_block_02
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_02/cool_block_02.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_02/cool_block_02_run.log 2>&1 \
  && log_done cool_block_02 \
  || { log_fail cool_block_02; sentinel_fail cool_block_02; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_02\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 3/14: cool_block_03 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_03
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_03
log_start cool_block_03
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_03/cool_block_03.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_03/cool_block_03_run.log 2>&1 \
  && log_done cool_block_03 \
  || { log_fail cool_block_03; sentinel_fail cool_block_03; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_03\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 4/14: cool_block_04 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_04
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_04
log_start cool_block_04
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_04/cool_block_04.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_04/cool_block_04_run.log 2>&1 \
  && log_done cool_block_04 \
  || { log_fail cool_block_04; sentinel_fail cool_block_04; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_04\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 5/14: cool_block_05 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_05
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_05
log_start cool_block_05
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_05/cool_block_05.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_05/cool_block_05_run.log 2>&1 \
  && log_done cool_block_05 \
  || { log_fail cool_block_05; sentinel_fail cool_block_05; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_05\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 6/14: cool_block_06 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_06
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_06
log_start cool_block_06
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_06/cool_block_06.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_06/cool_block_06_run.log 2>&1 \
  && log_done cool_block_06 \
  || { log_fail cool_block_06; sentinel_fail cool_block_06; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_06\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 7/14: cool_block_07 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_07
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_07
log_start cool_block_07
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_07/cool_block_07.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_07/cool_block_07_run.log 2>&1 \
  && log_done cool_block_07 \
  || { log_fail cool_block_07; sentinel_fail cool_block_07; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_07\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 8/14: cool_block_08 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_08
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_08
log_start cool_block_08
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_08/cool_block_08.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_08/cool_block_08_run.log 2>&1 \
  && log_done cool_block_08 \
  || { log_fail cool_block_08; sentinel_fail cool_block_08; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_08\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 9/14: cool_block_09 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_09
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_09
log_start cool_block_09
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_09/cool_block_09.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_09/cool_block_09_run.log 2>&1 \
  && log_done cool_block_09 \
  || { log_fail cool_block_09; sentinel_fail cool_block_09; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_09\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 10/14: cool_block_10 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_10
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_10
log_start cool_block_10
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_10/cool_block_10.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_10/cool_block_10_run.log 2>&1 \
  && log_done cool_block_10 \
  || { log_fail cool_block_10; sentinel_fail cool_block_10; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_10\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 11/14: cool_block_11 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_11
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_11
log_start cool_block_11
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_11/cool_block_11.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_11/cool_block_11_run.log 2>&1 \
  && log_done cool_block_11 \
  || { log_fail cool_block_11; sentinel_fail cool_block_11; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_11\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 12/14: cool_block_12 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_12
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_12
log_start cool_block_12
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_12/cool_block_12.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_12/cool_block_12_run.log 2>&1 \
  && log_done cool_block_12 \
  || { log_fail cool_block_12; sentinel_fail cool_block_12; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_12\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 13/14: cool_block_13 ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_13
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_13
log_start cool_block_13
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_13/cool_block_13.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/cool_block_13/cool_block_13_run.log 2>&1 \
  && log_done cool_block_13 \
  || { log_fail cool_block_13; sentinel_fail cool_block_13; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"cool_block_13\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 14/14: npt_final ---
mkdir -p /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/npt_final
cd /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/npt_final
log_start npt_final
$LAMMPS_LAUNCH -in /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/npt_final/npt_final.in >> /home/arz2/PolyJarvis_v2/data/PLLA_1/attempts/cooling/attempt-0002/work/npt_final/npt_final_run.log 2>&1 \
  && log_done npt_final \
  || { log_fail npt_final; sentinel_fail npt_final; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_final\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":14,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
sentinel_ok
rm -f "$PIDFILE"

