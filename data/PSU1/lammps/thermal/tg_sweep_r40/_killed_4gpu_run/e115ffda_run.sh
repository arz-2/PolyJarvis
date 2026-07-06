#!/bin/bash
export CUDA_VISIBLE_DEVICES=0,1,2,3
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_e115ffda
cd /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_40Kns
mpirun -np 4 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 4 -in /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_40Kns/tg_sweep_rate40.in >> /home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_40Kns/e115ffda_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"e115ffda","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PSU1/lammps/thermal/tg_sweep/rate_40Kns"}' > /tmp/polyjarvis/sentinels/done_e115ffda.json
else
  echo '{"run_id":"e115ffda","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_e115ffda.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_e115ffda

