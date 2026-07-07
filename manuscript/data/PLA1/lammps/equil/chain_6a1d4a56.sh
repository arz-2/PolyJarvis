#!/bin/bash
# PolyJarvis chain 6a1d4a56 — auto-generated, do not edit
set -euo pipefail

CHAIN_ID=6a1d4a56
LMP=/home/arz2/lammps-install/bin/lmp
MPI=1
GPU_IDS=2
N_GPU=1

# Progress log — one JSON object per line
PROGRESS=/home/arz2/PolyJarvis/data/PLA1/lammps/equil/chain_6a1d4a56_progress.jsonl

log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }

export CUDA_VISIBLE_DEVICES=2

# --- Stage 1/9: minimize ---
mkdir -p /home/arz2/PolyJarvis/data/PLA1/lammps/equil/minimize
cd /home/arz2/PolyJarvis/data/PLA1/lammps/equil/minimize
log_start minimize
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/PLA1/lammps/equil/minimize/minimize.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/equil/minimize/minimize.log 2>&1 \
  && log_done minimize \
  || { log_fail minimize; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"minimize\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 2/9: nvt_softheat ---
mkdir -p /home/arz2/PolyJarvis/data/PLA1/lammps/equil/nvt_softheat
cd /home/arz2/PolyJarvis/data/PLA1/lammps/equil/nvt_softheat
log_start nvt_softheat
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/PLA1/lammps/equil/nvt_softheat/nvt_softheat.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/equil/nvt_softheat/nvt_softheat.log 2>&1 \
  && log_done nvt_softheat \
  || { log_fail nvt_softheat; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"nvt_softheat\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 3/9: npt_compress ---
mkdir -p /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_compress
cd /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_compress
log_start npt_compress
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_compress/npt_compress.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_compress/npt_compress.log 2>&1 \
  && log_done npt_compress \
  || { log_fail npt_compress; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_compress\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 4/9: npt_pppm ---
mkdir -p /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_pppm
cd /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_pppm
log_start npt_pppm
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_pppm/npt_pppm.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_pppm/npt_pppm.log 2>&1 \
  && log_done npt_pppm \
  || { log_fail npt_pppm; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_pppm\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 5/9: npt_cool ---
mkdir -p /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_cool
cd /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_cool
log_start npt_cool
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_cool/npt_cool.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_cool/npt_cool.log 2>&1 \
  && log_done npt_cool \
  || { log_fail npt_cool; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_cool\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 6/9: nvt_production ---
mkdir -p /home/arz2/PolyJarvis/data/PLA1/lammps/equil/nvt_production
cd /home/arz2/PolyJarvis/data/PLA1/lammps/equil/nvt_production
log_start nvt_production
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/PLA1/lammps/equil/nvt_production/nvt_production.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/equil/nvt_production/nvt_production.log 2>&1 \
  && log_done nvt_production \
  || { log_fail nvt_production; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"nvt_production\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 7/9: npt_production ---
mkdir -p /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_production
cd /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_production
log_start npt_production
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_production/npt_production.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_production/npt_production.log 2>&1 \
  && log_done npt_production \
  || { log_fail npt_production; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_production\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 8/9: npt_cool300 ---
mkdir -p /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_cool300
cd /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_cool300
log_start npt_cool300
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_cool300/npt_cool300.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_cool300/npt_cool300.log 2>&1 \
  && log_done npt_cool300 \
  || { log_fail npt_cool300; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_cool300\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 9/9: npt_prod300 ---
mkdir -p /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_prod300
cd /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_prod300
log_start npt_prod300
mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU -in /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_prod300/npt_prod300.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/equil/npt_prod300/npt_prod300.log 2>&1 \
  && log_done npt_prod300 \
  || { log_fail npt_prod300; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_prod300\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":9,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"

