#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_2789b578
cd /home/arz2/PolyJarvis/data/PSU2/lammps/thermal/tg_sweep_rec1_r40
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PSU2/lammps/thermal/tg_sweep_rec1_r40/tg_sweep.in >> /home/arz2/PolyJarvis/data/PSU2/lammps/thermal/tg_sweep_rec1_r40/2789b578_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"2789b578","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PSU2/lammps/thermal/tg_sweep_rec1_r40"}' > /tmp/polyjarvis/sentinels/done_2789b578.json
else
  echo '{"run_id":"2789b578","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_2789b578.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_2789b578

