#!/bin/bash
# PolyJarvis manual BM chain — recovery for failed 2f290375 (server log-path + FF bugs, R-03)
# Scripts derived from the proven equil npt_production.in (correct TraPPE-UA FF).
set -uo pipefail

CHAIN_ID=2f290375b
LMP=/home/arz2/lammps-install/bin/lmp
BASE=/home/arz2/PolyJarvis/data/PE1/lammps/mechanical/bm_series
PROGRESS=$BASE/chain_${CHAIN_ID}_progress.jsonl
mkdir -p /tmp/polyjarvis/sentinels
SENTINEL=/tmp/polyjarvis/sentinels/done_${CHAIN_ID}.json
PIDFILE=/tmp/polyjarvis/sentinels/pid_${CHAIN_ID}
echo $$ > "$PIDFILE"

export CUDA_VISIBLE_DEVICES=1

ev(){ echo "{\"stage\":\"$1\",\"status\":\"$2\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }

for P in 1 100 300 600 1000; do
  d=$BASE/bm_P${P}
  cd "$d"
  ev bm_P${P} running
  mpirun -np 1 $LMP -sf gpu -pk gpu 1 -in "$d/bm_P${P}.in" >> "$d/bm_P${P}_run.log" 2>&1 \
    && ev bm_P${P} done \
    || { ev bm_P${P} failed; echo "{\"run_id\":\"${CHAIN_ID}\",\"status\":\"failed\",\"stage\":\"bm_P${P}\"}" > "$SENTINEL"; rm -f "$PIDFILE"; exit 1; }
done

ev __chain__ completed
echo "{\"run_id\":\"${CHAIN_ID}\",\"status\":\"completed\",\"n_stages\":5}" > "$SENTINEL"
rm -f "$PIDFILE"
