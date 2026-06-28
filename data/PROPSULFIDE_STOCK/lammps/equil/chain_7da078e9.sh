#!/bin/bash
# PolyJarvis chain 7da078e9 — auto-generated, do not edit (engine=gpu)
set -euo pipefail

CHAIN_ID=7da078e9
LMP=/home/alexzhao/lammps-install/bin/lmp
OFFLOAD_FLAGS="-sf gpu -pk gpu 1"
MPI=8
GPU_IDS=0
N_GPU=1

# Progress log — one JSON object per line
PROGRESS=/home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/chain_7da078e9_progress.jsonl

log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }

# Completion sentinel — written by THIS nohup'd script so it survives an
# MCP-server restart (the in-process chain monitor is only a fast-path).
mkdir -p /tmp/polyjarvis/sentinels
SENTINEL=/tmp/polyjarvis/sentinels/done_7da078e9.json
PIDFILE=/tmp/polyjarvis/sentinels/pid_7da078e9
sentinel_ok()   { echo "{\"run_id\":\"7da078e9\",\"status\":\"completed\"}" > "$SENTINEL"; }
sentinel_fail() { echo "{\"run_id\":\"7da078e9\",\"status\":\"failed\",\"stage\":\"$1\"}" > "$SENTINEL"; }

export CUDA_VISIBLE_DEVICES=0
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
# Record our own PID so watch_run can check liveness ($$ is the long-lived chain).
echo $$ > "$PIDFILE"
LAMMPS_LAUNCH="mpirun -np $MPI $LMP $OFFLOAD_FLAGS"

# --- Stage 1/7: minimize ---
mkdir -p /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/minimize
cd /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/minimize
log_start minimize
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/minimize/minimize.in >> /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/minimize/minimize_run.log 2>&1 \
  && log_done minimize \
  || { log_fail minimize; sentinel_fail minimize; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"minimize\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 2/7: nvt_softheat ---
mkdir -p /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/nvt_softheat
cd /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/nvt_softheat
log_start nvt_softheat
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/nvt_softheat/nvt_softheat.in >> /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/nvt_softheat/nvt_softheat_run.log 2>&1 \
  && log_done nvt_softheat \
  || { log_fail nvt_softheat; sentinel_fail nvt_softheat; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"nvt_softheat\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 3/7: npt_compress ---
mkdir -p /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_compress
cd /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_compress
log_start npt_compress
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_compress/npt_compress.in >> /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_compress/npt_compress_run.log 2>&1 \
  && log_done npt_compress \
  || { log_fail npt_compress; sentinel_fail npt_compress; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_compress\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 4/7: npt_pppm ---
mkdir -p /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_pppm
cd /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_pppm
log_start npt_pppm
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_pppm/npt_pppm.in >> /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_pppm/npt_pppm_run.log 2>&1 \
  && log_done npt_pppm \
  || { log_fail npt_pppm; sentinel_fail npt_pppm; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_pppm\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 5/7: npt_cool ---
mkdir -p /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_cool
cd /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_cool
log_start npt_cool
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_cool/npt_cool.in >> /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_cool/npt_cool_run.log 2>&1 \
  && log_done npt_cool \
  || { log_fail npt_cool; sentinel_fail npt_cool; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_cool\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 6/7: nvt_production ---
mkdir -p /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/nvt_production
cd /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/nvt_production
log_start nvt_production
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/nvt_production/nvt_production.in >> /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/nvt_production/nvt_production_run.log 2>&1 \
  && log_done nvt_production \
  || { log_fail nvt_production; sentinel_fail nvt_production; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"nvt_production\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 7/7: npt_production ---
mkdir -p /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_production
cd /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_production
log_start npt_production
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_production/npt_production.in >> /home/alexzhao/PolyJarvis/data/PROPSULFIDE_STOCK/lammps/equil/npt_production/npt_production_run.log 2>&1 \
  && log_done npt_production \
  || { log_fail npt_production; sentinel_fail npt_production; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_production\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":7,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
sentinel_ok
rm -f "$PIDFILE"

