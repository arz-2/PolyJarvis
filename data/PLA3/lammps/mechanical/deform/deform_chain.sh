#!/bin/bash
# Sequential x → y → z deform chain for PLA3
# Writes combined sentinel when all 3 complete

export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels

DEFORM_BASE=/home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform
LMP=/home/arz2/lammps-install-kokkos/bin/lmp
COMBINED_SENTINEL=/tmp/polyjarvis/sentinels/done_deform_PLA3.json

echo $$ > /tmp/polyjarvis/sentinels/pid_deform_PLA3

run_dir() {
  local dir=$1 logname=$2
  echo "[deform_chain] Starting $dir @ $(date)"
  cd $DEFORM_BASE/$dir
  env CUDA_VISIBLE_DEVICES=1 $LMP -k on g 1 -sf kk -pk kokkos \
    -in $logname.in >> ${logname}_chain.stdout 2>&1
  local RC=$?
  echo "[deform_chain] $dir exit=$RC @ $(date)"
  return $RC
}

run_dir x 05_deform_x && \
run_dir y 05_deform_y && \
run_dir z 05_deform_z

RC=$?
if [ $RC -eq 0 ]; then
  echo '{"status":"completed","dirs":["x","y","z"]}' > $COMBINED_SENTINEL
else
  echo '{"status":"failed","exit_code":"'$RC'"}' > $COMBINED_SENTINEL
fi
rm -f /tmp/polyjarvis/sentinels/pid_deform_PLA3
