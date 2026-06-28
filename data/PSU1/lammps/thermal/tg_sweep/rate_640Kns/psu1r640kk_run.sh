#!/bin/bash
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_psu1r640kk
source /home/arz2/miniforge3/etc/profile.d/conda.sh
conda activate mol-builder
cd /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_640Kns
env CUDA_VISIBLE_DEVICES=3 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos \
  -in /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_640Kns/tg_sweep_rate640.in \
  >> /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_640Kns/psu1r640kk_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"psu1r640kk","status":"completed"}' > /tmp/polyjarvis/sentinels/done_psu1r640kk.json
else
  echo '{"run_id":"psu1r640kk","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_psu1r640kk.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_psu1r640kk
