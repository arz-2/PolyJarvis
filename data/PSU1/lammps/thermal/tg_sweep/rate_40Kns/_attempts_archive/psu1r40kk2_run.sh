#!/bin/bash
export CUDA_VISIBLE_DEVICES=2
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_psu1r40kk2
cd /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_40Kns
source /home/arz2/miniforge3/etc/profile.d/conda.sh && conda activate mol-builder
mpirun -np 1 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_40Kns/tg_sweep_rate40.in >> /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_40Kns/psu1r40kk2_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"psu1r40kk2","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_40Kns"}' > /tmp/polyjarvis/sentinels/done_psu1r40kk2.json
else
  echo '{"run_id":"psu1r40kk2","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_psu1r40kk2.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_psu1r40kk2
