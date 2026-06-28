#!/bin/bash
# PolyJarvis chain 27af49b8 — P1000 only restart on GPU 1
set -euo pipefail

LMP=/home/arz2/lammps-install-kokkos/bin/lmp
OFFLOAD_FLAGS="-k on g 1 -sf kk -pk kokkos"
GPU_IDS=1

PROGRESS=/home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/chain_27af49b8_progress.jsonl

log_done()  { echo "{\"stage\":\"$1\",\"status\":\"done\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }
log_fail()  { echo "{\"stage\":\"$1\",\"status\":\"failed\",\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"; }

mkdir -p /tmp/polyjarvis/sentinels
SENTINEL=/tmp/polyjarvis/sentinels/done_27af49b8.json
PIDFILE=/tmp/polyjarvis/sentinels/pid_27af49b8
sentinel_ok()   { echo "{\"run_id\":\"27af49b8\",\"status\":\"completed\"}" > "$SENTINEL"; }
sentinel_fail() { echo "{\"run_id\":\"27af49b8\",\"status\":\"failed\",\"stage\":\"$1\"}" > "$SENTINEL"; }

export CUDA_VISIBLE_DEVICES=$GPU_IDS
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
echo $$ > "$PIDFILE"

# Pre-seed progress with the 4 already-completed stages (P-1000, P-500, P0, P500)
cat > "$PROGRESS" <<'EOF'
{"stage":"bm_P-1000","status":"done","ts":"2026-06-24T03:44:00"}
{"stage":"bm_P-500","status":"done","ts":"2026-06-24T04:51:00"}
{"stage":"bm_P0","status":"done","ts":"2026-06-24T05:24:00"}
{"stage":"bm_P500","status":"done","ts":"2026-06-24T09:46:00"}
EOF

# --- Stage 5/5: bm_P1000 ---
cd /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/bm_P1000
env CUDA_VISIBLE_DEVICES=$GPU_IDS $LMP $OFFLOAD_FLAGS \
  -in /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/bm_P1000/bm_P1000.in \
  >> /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/bm_series/bm_P1000/bm_P1000.log 2>&1 \
  && log_done bm_P1000 \
  || { log_fail bm_P1000; sentinel_fail bm_P1000; exit 1; }

echo "{\"stage\":\"__chain__\",\"status\":\"completed\",\"n_stages\":5,\"ts\":\"$(date -Iseconds)\"}" >> "$PROGRESS"
sentinel_ok
rm -f "$PIDFILE"
