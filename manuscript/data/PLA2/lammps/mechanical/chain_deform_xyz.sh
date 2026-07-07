#!/bin/bash
# PolyJarvis — PLA2 deform 3-direction chain (x→y→z), PCFF KOKKOS GPU 1
set -euo pipefail

LMP=/home/arz2/lammps-install-kokkos/bin/lmp
KOKKOS_FLAGS="-k on g 1 -sf kk -pk kokkos"
BASE=/home/arz2/PolyJarvis/data/PLA2/lammps/mechanical

export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX

mkdir -p /tmp/polyjarvis/sentinels
SENTINEL=/tmp/polyjarvis/sentinels/done_deform_pla2.json
PIDFILE=/tmp/polyjarvis/sentinels/pid_deform_pla2
echo $$ > "$PIDFILE"

run_stage() {
  local dir=$1
  echo "[$(date -Iseconds)] Starting deform_${dir}"
  cd "$BASE/deform_${dir}"
  rm -f 05_deform.log log.lammps 05_deform_out.data
  env CUDA_VISIBLE_DEVICES=1 $LMP $KOKKOS_FLAGS \
    -in "$BASE/deform_${dir}/05_deform.in" \
    >> "$BASE/deform_${dir}/05_deform.log" 2>&1
  echo "[$(date -Iseconds)] Done deform_${dir}"
}

run_stage x
run_stage y
run_stage z

echo "{\"run_id\":\"deform_pla2\",\"status\":\"completed\",\"ts\":\"$(date -Iseconds)\"}" > "$SENTINEL"
rm -f "$PIDFILE"
