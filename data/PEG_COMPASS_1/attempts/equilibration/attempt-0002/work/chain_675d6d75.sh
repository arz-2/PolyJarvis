#!/bin/bash
# PolyJarvis chain 675d6d75 — auto-generated, do not edit (engine=kokkos)
set -euo pipefail

CHAIN_ID=675d6d75
LMP=/home/alexzhao/lammps-install-kokkos/bin/lmp
OFFLOAD_FLAGS="-k on g 1 -sf kk -pk kokkos"
MPI=1
GPU_IDS=0
N_GPU=1

# Progress log — one JSON object per line
PROGRESS=/home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/chain_675d6d75_progress.jsonl

log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_start() { echo "{\"stage\":\"$1\",\"status\":\"running\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }

# Completion sentinel — written by THIS nohup'd script so it survives an
# MCP-server restart (the in-process chain monitor is only a fast-path).
mkdir -p /tmp/polyjarvis/sentinels
SENTINEL=/tmp/polyjarvis/sentinels/done_675d6d75.json
PIDFILE=/tmp/polyjarvis/sentinels/pid_675d6d75
sentinel_ok()   { echo "{\"run_id\":\"675d6d75\",\"status\":\"completed\"}" > "$SENTINEL"; }
sentinel_fail() { echo "{\"run_id\":\"675d6d75\",\"status\":\"failed\",\"stage\":\"$1\"}" > "$SENTINEL"; }

export CUDA_VISIBLE_DEVICES=0
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
# Record our own PID so watch_run can check liveness ($$ is the long-lived chain).
echo $$ > "$PIDFILE"
LAMMPS_LAUNCH="env CUDA_VISIBLE_DEVICES=$GPU_IDS $LMP $OFFLOAD_FLAGS"

# --- Stage 1/10: minimize ---
mkdir -p /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/minimize
cd /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/minimize
log_start minimize
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/minimize/minimize.in >> /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/minimize/minimize_run.log 2>&1 \
  && log_done minimize \
  || { log_fail minimize; sentinel_fail minimize; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"minimize\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Minimization-convergence check (not itself a LAMMPS exit-code failure) ---
if ! grep -Eq "Stopping criterion.*(tolerance|linesearch alpha is zero)" /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/minimize/minimize_run.log; then
  log_fail minimize; sentinel_fail minimize_not_converged; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",""\"failed_at\":\"minimize\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1
fi

# --- Stage 2/10: nvt_warmup ---
mkdir -p /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/nvt_warmup
cd /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/nvt_warmup
log_start nvt_warmup
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/nvt_warmup/nvt_warmup.in >> /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/nvt_warmup/nvt_warmup_run.log 2>&1 \
  && log_done nvt_warmup \
  || { log_fail nvt_warmup; sentinel_fail nvt_warmup; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"nvt_warmup\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 3/10: npt_densify ---
mkdir -p /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_densify
cd /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_densify
log_start npt_densify
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_densify/npt_densify.in >> /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_densify/npt_densify_run.log 2>&1 \
  && log_done npt_densify \
  || { log_fail npt_densify; sentinel_fail npt_densify; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_densify\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 4/10: npt_ff_activate ---
mkdir -p /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_ff_activate
cd /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_ff_activate
log_start npt_ff_activate
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_ff_activate/npt_ff_activate.in >> /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_ff_activate/npt_ff_activate_run.log 2>&1 \
  && log_done npt_ff_activate \
  || { log_fail npt_ff_activate; sentinel_fail npt_ff_activate; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_ff_activate\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 5/10: npt_densify_hold ---
mkdir -p /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_densify_hold
cd /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_densify_hold
log_start npt_densify_hold
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_densify_hold/npt_densify_hold.in >> /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_densify_hold/npt_densify_hold_run.log 2>&1 \
  && log_done npt_densify_hold \
  || { log_fail npt_densify_hold; sentinel_fail npt_densify_hold; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_densify_hold\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 6/10: anneal_heat ---
mkdir -p /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/anneal_heat
cd /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/anneal_heat
log_start anneal_heat
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/anneal_heat/anneal_heat.in >> /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/anneal_heat/anneal_heat_run.log 2>&1 \
  && log_done anneal_heat \
  || { log_fail anneal_heat; sentinel_fail anneal_heat; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"anneal_heat\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 7/10: anneal_hold ---
mkdir -p /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/anneal_hold
cd /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/anneal_hold
log_start anneal_hold
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/anneal_hold/anneal_hold.in >> /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/anneal_hold/anneal_hold_run.log 2>&1 \
  && log_done anneal_hold \
  || { log_fail anneal_hold; sentinel_fail anneal_hold; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"anneal_hold\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 8/10: npt_melt_ramp ---
mkdir -p /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_melt_ramp
cd /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_melt_ramp
log_start npt_melt_ramp
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_melt_ramp/npt_melt_ramp.in >> /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_melt_ramp/npt_melt_ramp_run.log 2>&1 \
  && log_done npt_melt_ramp \
  || { log_fail npt_melt_ramp; sentinel_fail npt_melt_ramp; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_melt_ramp\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 9/10: nvt_melt_hold ---
mkdir -p /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/nvt_melt_hold
cd /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/nvt_melt_hold
log_start nvt_melt_hold
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/nvt_melt_hold/nvt_melt_hold.in >> /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/nvt_melt_hold/nvt_melt_hold_run.log 2>&1 \
  && log_done nvt_melt_hold \
  || { log_fail nvt_melt_hold; sentinel_fail nvt_melt_hold; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"nvt_melt_hold\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

# --- Stage 10/10: npt_melt_hold ---
mkdir -p /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_melt_hold
cd /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_melt_hold
log_start npt_melt_hold
$LAMMPS_LAUNCH -in /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_melt_hold/npt_melt_hold.in >> /home/alexzhao/PolyJarvis/data/PEG_COMPASS_1/attempts/equilibration/attempt-0002/work/npt_melt_hold/npt_melt_hold_run.log 2>&1 \
  && log_done npt_melt_hold \
  || { log_fail npt_melt_hold; sentinel_fail npt_melt_hold; echo "{\"stage\":\"__chain__\",\"status\":\"failed\",\"failed_at\":\"npt_melt_hold\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; exit 1; }

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":10,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
sentinel_ok
rm -f "$PIDFILE"

