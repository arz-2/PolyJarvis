#!/bin/bash
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_psu1r160kk
source /home/arz2/miniforge3/etc/profile.d/conda.sh
conda activate mol-builder
cd /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_160Kns
env CUDA_VISIBLE_DEVICES=2 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos \
  -in /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_160Kns/tg_sweep_rate160.in \
  >> /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_160Kns/psu1r160kk_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"psu1r160kk","status":"completed"}' > /tmp/polyjarvis/sentinels/done_psu1r160kk.json
else
  echo '{"run_id":"psu1r160kk","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_psu1r160kk.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_psu1r160kk
