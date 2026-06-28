#!/bin/bash
# PolyJarvis chain c2e7c43e — auto-generated, do not edit
set -euo pipefail

CHAIN_ID=c2e7c43e
LMP=/home/arz2/lammps-install/bin/lmp
MPI=1
GPU_IDS=2
N_GPU=1

# Progress log — one JSON object per line
PROGRESS=/home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/chain_c2e7c43e_progress.jsonl

log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }

# Completion sentinel — written by THIS nohup'd script so it survives an
# MCP-server restart (the in-process chain monitor is only a fast-path).
mkdir -p /tmp/polyjarvis/sentinels
SENTINEL=/tmp/polyjarvis/sentinels/done_c2e7c43e.json
PIDFILE=/tmp/polyjarvis/sentinels/pid_c2e7c43e
sentinel_ok()   { echo "{\"run_id\":\"c2e7c43e\",\"status\":\"completed\"}" > "$SENTINEL"; }
sentinel_fail() { echo "{\"run_id\":\"c2e7c43e\",\"status\":\"failed\",\"stage\":\"$1\"}" > "$SENTINEL"; }

export CUDA_VISIBLE_DEVICES=2
# Record our own PID so watch_run can check liveness ($$ is the long-lived chain).
echo $$ > "$PIDFILE"

# --- Stage 1/7: minimize ---
mkdir -p /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/minimize
cd /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/minimize
log_start minimize
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/minimize/minimize.in >> /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/minimize/minimize.log 2>&1 \
  && log_done minimize \
  || { log_fail minimize; sentinel_fail minimize; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"minimize\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 2/7: nvt_softheat ---
mkdir -p /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/nvt_softheat
cd /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/nvt_softheat
log_start nvt_softheat
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/nvt_softheat/nvt_softheat.in >> /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/nvt_softheat/nvt_softheat.log 2>&1 \
  && log_done nvt_softheat \
  || { log_fail nvt_softheat; sentinel_fail nvt_softheat; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"nvt_softheat\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 3/7: npt_compress ---
mkdir -p /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_compress
cd /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_compress
log_start npt_compress
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_compress/npt_compress.in >> /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_compress/npt_compress.log 2>&1 \
  && log_done npt_compress \
  || { log_fail npt_compress; sentinel_fail npt_compress; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_compress\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 4/7: npt_pppm ---
mkdir -p /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_pppm
cd /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_pppm
log_start npt_pppm
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_pppm/npt_pppm.in >> /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_pppm/npt_pppm.log 2>&1 \
  && log_done npt_pppm \
  || { log_fail npt_pppm; sentinel_fail npt_pppm; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_pppm\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 5/7: npt_cool ---
mkdir -p /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_cool
cd /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_cool
log_start npt_cool
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_cool/npt_cool.in >> /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_cool/npt_cool.log 2>&1 \
  && log_done npt_cool \
  || { log_fail npt_cool; sentinel_fail npt_cool; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_cool\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 6/7: nvt_production ---
mkdir -p /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/nvt_production
cd /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/nvt_production
log_start nvt_production
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/nvt_production/nvt_production.in >> /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/nvt_production/nvt_production.log 2>&1 \
  && log_done nvt_production \
  || { log_fail nvt_production; sentinel_fail nvt_production; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"nvt_production\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 7/7: npt_production ---
mkdir -p /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_production
cd /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_production
log_start npt_production
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_production/npt_production.in >> /home/arz2/PolyJarvis/data/cis-PBD1/lammps/equil/npt_production/npt_production.log 2>&1 \
  && log_done npt_production \
  || { log_fail npt_production; sentinel_fail npt_production; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_production\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":7,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
sentinel_ok
rm -f "$PIDFILE"

