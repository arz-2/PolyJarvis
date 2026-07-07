#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_02bab4f6
cd /home/arz2/PolyJarvis/data/PLA3/lammps/thermal/tg_sweep_r25
env CUDA_VISIBLE_DEVICES=1 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PLA3/lammps/thermal/tg_sweep_r25/tg_sweep.in >> /home/arz2/PolyJarvis/data/PLA3/lammps/thermal/tg_sweep_r25/02bab4f6_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"02bab4f6","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA3/lammps/thermal/tg_sweep_r25"}' > /tmp/polyjarvis/sentinels/done_02bab4f6.json
else
  echo '{"run_id":"02bab4f6","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_02bab4f6.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_02bab4f6

