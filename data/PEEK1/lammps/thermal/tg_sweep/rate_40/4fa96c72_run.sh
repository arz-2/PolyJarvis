#!/bin/bash
export CUDA_VISIBLE_DEVICES=0,2,3
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_4fa96c72
cd /home/arz2/PolyJarvis/data/PEEK1/lammps/thermal/tg_sweep/rate_40
mpirun -np 3 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 3 -in /home/arz2/PolyJarvis/data/PEEK1/lammps/thermal/tg_sweep/rate_40/tg_sweep.in >> /home/arz2/PolyJarvis/data/PEEK1/lammps/thermal/tg_sweep/rate_40/4fa96c72_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"4fa96c72","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PEEK1/lammps/thermal/tg_sweep/rate_40"}' > /tmp/polyjarvis/sentinels/done_4fa96c72.json
else
  echo '{"run_id":"4fa96c72","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_4fa96c72.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_4fa96c72

