#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_d94a548f
cd /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_40Kns
mpirun -np 4 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_40Kns/tg_sweep_rate40.in >> /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_40Kns/d94a548f_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"d94a548f","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_40Kns"}' > /tmp/polyjarvis/sentinels/done_d94a548f.json
else
  echo '{"run_id":"d94a548f","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_d94a548f.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_d94a548f

